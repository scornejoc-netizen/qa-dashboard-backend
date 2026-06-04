"""
Endpoints DRF para el dashboard gerencial de desarrolladores.

Convención: function-based views con @api_view, igual que la app `metrics`.
Todos los endpoints son GET / read-only — la escritura se hace en el admin.

Filtro temporal: el parámetro `month` (YYYY-MM) es OPCIONAL.
- Sin `month` → se consideran TODOS los requerimientos (totales históricos).
- Con `month` → se filtran los requerimientos creados O entregados en ese mes.
"""
import statistics
from datetime import date
from django.db.models import Sum, Q
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Developer, Requirement, TestExecution, UserStory
from .serializers import (
    DeveloperSerializer,
    RequirementDetailSerializer,
)


# ---------------- Helpers ----------------

def _parse_month_optional(request):
    """Devuelve (year, month) o (None, None) si no se pasó el parámetro."""
    raw = (request.query_params.get('month') or '').strip()
    if not raw:
        return None, None
    try:
        y, m = raw.split('-')
        y, m = int(y), int(m)
        if not (1 <= m <= 12):
            raise ValueError
        return y, m
    except (ValueError, AttributeError, TypeError):
        return None, None


def _filter_reqs_by_month(qs, year, month):
    """Filtra requerimientos creados O entregados en el mes. Sin mes → sin filtro."""
    if year is None or month is None:
        return qs
    return qs.filter(
        Q(created_at__year=year, created_at__month=month)
        | Q(delivered_at__year=year, delivered_at__month=month)
    )


def _weighted_quality_for_reqs(req_ids):
    """% ponderado de tests pasados para una lista de IDs de requerimiento."""
    agg = TestExecution.objects.filter(requirement_id__in=req_ids).aggregate(
        total=Sum('total'), passed=Sum('passed')
    )
    total = agg['total'] or 0
    passed = agg['passed'] or 0
    if total == 0:
        return None, total, passed
    return round(passed / total * 100, 1), total, passed


def _status_counts(reqs):
    """Cuenta requerimientos por estado, agrupados en 3 buckets gerenciales + detalle."""
    counts = {s: 0 for s in ('todo', 'in_progress', 'qa', 'done', 'released')}
    for status in reqs.values_list('status', flat=True):
        if status in counts:
            counts[status] += 1
    return {
        'por_hacer': counts['todo'],
        'en_desarrollo': counts['in_progress'] + counts['qa'],
        'entregados': counts['done'] + counts['released'],
        'detail': counts,
    }


def _deviation_metrics(items):
    """Estadísticas de desviación de tiempo (entrega real − planificada).

    Acepta cualquier iterable cuyos elementos tengan la propiedad
    `time_deviation_days` — actualmente usado con UserStory (predicción por HU).
    """
    deviations = [i.time_deviation_days for i in items if i.time_deviation_days is not None]
    if not deviations:
        return {
            'avg_deviation_days': None,
            'median_deviation_days': None,
            'min_deviation_days': None,
            'max_deviation_days': None,
            'with_planning': 0,
            'delayed': 0,
            'on_time': 0,
            'early': 0,
        }
    return {
        'avg_deviation_days': round(sum(deviations) / len(deviations), 1),
        'median_deviation_days': round(statistics.median(deviations), 1),
        'min_deviation_days': min(deviations),
        'max_deviation_days': max(deviations),
        'with_planning': len(deviations),
        'delayed': sum(1 for d in deviations if d > 0),
        'on_time': sum(1 for d in deviations if d == 0),
        'early': sum(1 for d in deviations if d < 0),
    }


def _calculate_scorecard(developer, year, month):
    """Métricas de un desarrollador. Sin year/month considera TODOS sus requerimientos.

    La desviación se calcula a partir de las HISTORIAS DE USUARIO de los reqs,
    no a nivel requerimiento (porque las fechas planificadas/reales viven en la HU).
    """
    reqs = _filter_reqs_by_month(developer.requirements.all(), year, month)
    req_ids = list(reqs.values_list('id', flat=True))

    weighted_quality, total_tests, passed_tests = _weighted_quality_for_reqs(req_ids)

    delivered = reqs.filter(status__in=['done', 'released'])
    cycle_times = [r.cycle_time_days for r in reqs if r.cycle_time_days is not None]
    avg_cycle = round(sum(cycle_times) / len(cycle_times), 1) if cycle_times else None

    # Desviación a nivel HU
    hus = UserStory.objects.filter(requirement_id__in=req_ids)
    deviation = _deviation_metrics(hus)
    deviation['total_user_stories'] = hus.count()

    return {
        'total_requirements': reqs.count(),
        'requirements_delivered': delivered.count(),
        'status_counts': _status_counts(reqs),
        'deviation': deviation,
        'weighted_quality': weighted_quality,
        'qa_bounces_total': reqs.aggregate(s=Sum('qa_bounces'))['s'] or 0,
        'production_bugs_total': reqs.aggregate(s=Sum('production_bugs'))['s'] or 0,
        'avg_cycle_time_days': avg_cycle,
        'total_tests': total_tests,
        'passed_tests': passed_tests,
    }


# ---------------- Endpoints ----------------

@api_view(['GET'])
def developers_dashboard(request):
    """
    GET /api/developers/dashboard/?month=YYYY-MM  (month opcional)
    Devuelve KPIs globales + lista de devs con su scorecard.
    """
    year, month = _parse_month_optional(request)

    developers = Developer.objects.filter(active=True)
    total_devs = developers.count()

    # Solo incluimos en la lista a los devs con al menos 1 requerimiento en el período.
    # Los devs sin trabajo en ese mes no aparecen en la tabla del dashboard.
    dev_items = []
    for dev in developers:
        scorecard = _calculate_scorecard(dev, year, month)
        if scorecard['total_requirements'] > 0:
            dev_items.append({
                **DeveloperSerializer(dev).data,
                'scorecard': scorecard,
            })

    # KPIs globales — el total de requerimientos es DISTINCT (un req con N devs cuenta 1 vez)
    all_reqs = _filter_reqs_by_month(Requirement.objects.all(), year, month)
    all_req_ids = list(all_reqs.values_list('id', flat=True))
    global_quality, _, _ = _weighted_quality_for_reqs(all_req_ids)
    global_status = _status_counts(all_reqs)
    # Desviación global también a nivel HU
    all_hus = UserStory.objects.filter(requirement__in=all_reqs)
    global_deviation = _deviation_metrics(all_hus)
    global_deviation['total_user_stories'] = all_hus.count()

    global_kpis = {
        # Total de requerimientos del período (respeta el filtro de mes)
        'total_requirements': all_reqs.count(),
        'delivered_requirements': all_reqs.filter(status__in=['done', 'released']).count(),
        'avg_quality': global_quality,
        'total_qa_bounces': all_reqs.aggregate(s=Sum('qa_bounces'))['s'] or 0,
        'total_production_bugs': all_reqs.aggregate(s=Sum('production_bugs'))['s'] or 0,
        'active_developers_with_work': len(dev_items),
        'total_developers': total_devs,
    }

    # Datos listos para gráficos en el frontend
    charts = {
        'status_distribution': [
            {'name': 'Por hacer', 'value': global_status['por_hacer'], 'key': 'por_hacer'},
            {'name': 'En desarrollo', 'value': global_status['en_desarrollo'], 'key': 'en_desarrollo'},
            {'name': 'Entregados', 'value': global_status['entregados'], 'key': 'entregados'},
        ],
        'by_developer': [
            {
                'name': i['full_name'],
                'requerimientos': i['scorecard']['total_requirements'],
                'calidad': i['scorecard']['weighted_quality'],
                'desviacion': i['scorecard']['deviation']['avg_deviation_days'],
            }
            for i in dev_items if i['scorecard']['total_requirements'] > 0
        ],
    }

    return Response({
        'year': year,
        'month': month,
        'is_filtered': bool(year and month),
        'kpis': global_kpis,
        'global_status': global_status,
        'global_deviation': global_deviation,
        'charts': charts,
        'developers': dev_items,
    })


@api_view(['GET'])
def developer_detail(request, dev_id):
    """
    GET /api/developers/<id>/?month=YYYY-MM  (month opcional)
    Devuelve el scorecard del dev + TODOS sus requerimientos (cualquier estado),
    filtrados por mes solo si se pasa el parámetro.
    """
    developer = get_object_or_404(Developer, pk=dev_id)
    year, month = _parse_month_optional(request)

    scorecard = _calculate_scorecard(developer, year, month)

    requirements = (
        _filter_reqs_by_month(developer.requirements.all(), year, month)
        .prefetch_related('test_executions', 'developers')
    )

    return Response({
        'developer': DeveloperSerializer(developer).data,
        'year': year,
        'month': month,
        'is_filtered': bool(year and month),
        'scorecard': scorecard,
        'requirements': RequirementDetailSerializer(requirements, many=True).data,
    })


@api_view(['GET'])
def developers_health(request):
    """GET /api/developers/health/ — endpoint trivial para verificar que la app responde."""
    return Response({'status': 'ok', 'app': 'developers'})
