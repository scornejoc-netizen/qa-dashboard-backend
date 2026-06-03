"""
Admin de Django para el dashboard de desarrolladores.

Filosofía: el admin es la herramienta principal de captura manual mientras
no exista CI/CD que alimente los datos automáticamente. Por eso mostramos
todas las métricas derivadas (% ponderado, cycle time, etc.) directamente
en el list_display y en el detalle, sin requerir queries adicionales.
"""
from django.contrib import admin
from django.db.models import Sum
from django.utils.html import format_html
from .models import Developer, Sprint, Requirement, TestExecution, UserStory


def _quality_color(pct):
    """Devuelve un color HTML según el % de calidad."""
    if pct is None:
        return '#94a3b8'  # slate-400
    if pct >= 90:
        return '#16a34a'  # green-600
    if pct >= 75:
        return '#f59e0b'  # amber-500
    return '#dc2626'      # red-600


def _format_quality(pct):
    if pct is None:
        return format_html('<span style="color: #94a3b8;">{}</span>', '—')
    color = _quality_color(pct)
    return format_html(
        '<span style="color: {}; font-weight: 600;">{}%</span>',
        color, pct,
    )


class UserStoryInline(admin.StackedInline):
    model = UserStory
    extra = 0
    fields = (
        ('code', 'title', 'status'),
        'description',
        ('planned_start_date', 'planned_end_date'),
        ('started_at', 'delivered_at'),
        ('deviation_display',),
        'notes',
    )
    readonly_fields = ('deviation_display',)
    classes = ('collapse',)

    def deviation_display(self, obj):
        dev = obj.time_deviation_days
        if dev is None:
            return format_html('<span style="color: #94a3b8;">{}</span>', '— (falta planificada o real)')
        if dev > 0:
            return format_html('<span style="color: #dc2626; font-weight:600;">+{} días de atraso</span>', dev)
        if dev < 0:
            return format_html('<span style="color: #16a34a; font-weight:600;">{} días de adelanto</span>', dev)
        return format_html('<span style="color: #16a34a; font-weight:600;">{}</span>', 'A tiempo')
    deviation_display.short_description = 'Desviación calculada'


class TestExecutionInline(admin.TabularInline):
    model = TestExecution
    extra = 1
    fields = ('test_type', 'total', 'passed', 'failed_display', 'pass_pct_display', 'executed_at', 'notes')
    readonly_fields = ('failed_display', 'pass_pct_display')

    def failed_display(self, obj):
        if obj.pk is None:
            return '—'
        return obj.failed
    failed_display.short_description = 'Fallaron'

    def pass_pct_display(self, obj):
        if obj.pk is None:
            return '—'
        return format_html('<strong>{}%</strong>', obj.pass_pct)
    pass_pct_display.short_description = '% Éxito'


@admin.register(Developer)
class DeveloperAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'level_badge', 'email', 'active',
                    'requirements_count', 'avg_quality_display')
    list_filter = ('level', 'active')
    search_fields = ('full_name', 'email', 'github_username')
    list_per_page = 25
    fieldsets = (
        ('Identidad', {'fields': ('full_name', 'email', 'github_username')}),
        ('Estado', {'fields': ('level', 'active', 'joined_at')}),
    )

    def level_badge(self, obj):
        colors = {'junior': '#2563eb', 'mid': '#d97706', 'senior': '#059669'}
        bg = colors.get(obj.level, '#6b7280')
        return format_html(
            '<span style="background:{}; color:white; padding:3px 8px; '
            'border-radius:10px; font-size:11px; font-weight:600;">{}</span>',
            bg, obj.get_level_display(),
        )
    level_badge.short_description = 'Nivel'

    def requirements_count(self, obj):
        return obj.requirements.count()
    requirements_count.short_description = 'Req. asignados'

    def avg_quality_display(self, obj):
        """Promedio ponderado de TODOS sus requerimientos (histórico)."""
        agg = TestExecution.objects.filter(requirement__developers=obj).aggregate(
            total=Sum('total'),
            passed=Sum('passed'),
        )
        if not agg['total']:
            return _format_quality(None)
        pct = round(agg['passed'] / agg['total'] * 100, 1)
        return _format_quality(pct)
    avg_quality_display.short_description = 'Calidad histórica'


@admin.register(Sprint)
class SprintAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date', 'requirements_count')
    list_filter = ('start_date',)
    search_fields = ('name',)
    ordering = ('-start_date',)

    def requirements_count(self, obj):
        return obj.requirements.count()
    requirements_count.short_description = 'Requerimientos'


@admin.register(Requirement)
class RequirementAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'title_truncated', 'space', 'developers_display', 'type_badge', 'status_badge',
        'is_documented', 'qa_bounces', 'cycle_time_display', 'deviation_display',
        'tests_summary_display', 'weighted_quality_display', 'delivered_at',
    )
    list_filter = ('status', 'type', 'is_documented', 'developers', 'space', 'sprint', 'delivered_at')
    search_fields = ('code', 'title', 'space', 'developers__full_name')
    autocomplete_fields = ['developers', 'sprint']
    date_hierarchy = 'delivered_at'
    list_per_page = 30
    inlines = [UserStoryInline, TestExecutionInline]
    fieldsets = (
        ('Identificación', {
            'fields': ('code', 'title', 'space', 'description', 'jira_url'),
            'description': (
                'El código se auto-genera (REQ-NNN) si lo dejas vacío. '
                'El espacio corresponde al módulo funcional (ej: TUTOR_VIRTUAL).'
            ),
        }),
        ('Asignación', {
            'fields': ('developers', 'sprint', 'type', 'status'),
        }),
        ('Fechas planificadas (cronograma)', {
            'fields': ('planned_start_date', 'planned_end_date'),
            'description': 'Lo que se planificó. La entrega planificada se compara con la real para la desviación.',
        }),
        ('Fechas reales', {
            'fields': ('created_at', 'started_at', 'delivered_at', 'closed_at'),
            'description': 'Lo que ocurrió de verdad. Desviación = entrega real − entrega planificada.',
        }),
        ('Calidad', {
            'fields': ('qa_bounces', 'production_bugs', 'is_documented', 'notes'),
            'description': (
                'qa_bounces = cuántas veces el requerimiento volvió de QA al dev. '
                'production_bugs = bugs encontrados DESPUÉS del release. '
                'is_documented = marcar cuando exista documentación funcional/técnica.'
            ),
        }),
    )

    def title_truncated(self, obj):
        return obj.title if len(obj.title) <= 60 else obj.title[:57] + '...'
    title_truncated.short_description = 'Título'

    def developers_display(self, obj):
        names = [d.full_name for d in obj.developers.all()]
        if not names:
            return '—'
        if len(names) <= 2:
            return ', '.join(names)
        return f"{names[0]}, {names[1]} +{len(names) - 2}"
    developers_display.short_description = 'Desarrolladores'

    def type_badge(self, obj):
        colors = {
            'feature': '#2563eb', 'bug': '#dc2626',
            'tech_debt': '#7c3aed', 'improvement': '#059669',
        }
        bg = colors.get(obj.type, '#6b7280')
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; '
            'border-radius:4px; font-size:11px;">{}</span>',
            bg, obj.get_type_display(),
        )
    type_badge.short_description = 'Tipo'

    def status_badge(self, obj):
        colors = {
            'todo': '#6b7280', 'in_progress': '#2563eb',
            'qa': '#f59e0b', 'done': '#059669', 'released': '#16a34a',
        }
        bg = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; '
            'border-radius:4px; font-size:11px;">{}</span>',
            bg, obj.get_status_display(),
        )
    status_badge.short_description = 'Estado'

    def cycle_time_display(self, obj):
        ct = obj.cycle_time_days
        if ct is None:
            return '—'
        return f"{ct} d"
    cycle_time_display.short_description = 'T. entrega'

    def deviation_display(self, obj):
        dev = obj.time_deviation_days
        if dev is None:
            return format_html('<span style="color: #94a3b8;">{}</span>', '—')
        if dev > 0:
            return format_html('<span style="color: #dc2626; font-weight:600;">+{} d</span>', dev)
        if dev < 0:
            return format_html('<span style="color: #16a34a; font-weight:600;">{} d</span>', dev)
        return format_html('<span style="color: #16a34a; font-weight:600;">{}</span>', 'a tiempo')
    deviation_display.short_description = 'Desviación'

    def tests_summary_display(self, obj):
        return obj.tests_summary
    tests_summary_display.short_description = 'Pasaron/Total'

    def weighted_quality_display(self, obj):
        return _format_quality(obj.weighted_quality)
    weighted_quality_display.short_description = 'Calidad ponderada'


@admin.register(UserStory)
class UserStoryAdmin(admin.ModelAdmin):
    list_display = ('requirement', 'code', 'title_truncated', 'status_badge',
                    'planned_end_date', 'delivered_at', 'deviation_display')
    list_filter = ('status', 'requirement')
    search_fields = ('code', 'title', 'requirement__code', 'requirement__title')
    autocomplete_fields = ['requirement']
    fieldsets = (
        ('Identificación', {'fields': ('requirement', 'code', 'title', 'description', 'status')}),
        ('Fechas planificadas', {'fields': ('planned_start_date', 'planned_end_date')}),
        ('Fechas reales', {'fields': ('started_at', 'delivered_at')}),
        ('Notas', {'fields': ('notes',)}),
    )

    def title_truncated(self, obj):
        return obj.title if len(obj.title) <= 60 else obj.title[:57] + '...'
    title_truncated.short_description = 'Título'

    def status_badge(self, obj):
        colors = {
            'todo': '#6b7280', 'in_progress': '#2563eb',
            'qa': '#f59e0b', 'done': '#059669',
        }
        bg = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; '
            'border-radius:4px; font-size:11px;">{}</span>',
            bg, obj.get_status_display(),
        )
    status_badge.short_description = 'Estado'

    def deviation_display(self, obj):
        dev = obj.time_deviation_days
        if dev is None:
            return format_html('<span style="color: #94a3b8;">{}</span>', '—')
        if dev > 0:
            return format_html('<span style="color: #dc2626; font-weight:600;">+{} d</span>', dev)
        if dev < 0:
            return format_html('<span style="color: #16a34a; font-weight:600;">{} d</span>', dev)
        return format_html('<span style="color: #16a34a; font-weight:600;">{}</span>', 'a tiempo')
    deviation_display.short_description = 'Desviación'


@admin.register(TestExecution)
class TestExecutionAdmin(admin.ModelAdmin):
    list_display = ('requirement', 'test_type', 'total', 'passed',
                    'failed_display', 'pass_pct_display', 'executed_at')
    list_filter = ('test_type', 'executed_at')
    search_fields = ('requirement__code', 'requirement__title')
    autocomplete_fields = ['requirement']
    date_hierarchy = 'executed_at'

    def failed_display(self, obj):
        return obj.failed
    failed_display.short_description = 'Fallaron'

    def pass_pct_display(self, obj):
        return _format_quality(obj.pass_pct)
    pass_pct_display.short_description = '% Éxito'


# Personalización del header del admin
admin.site.site_header = 'QA Dashboard — Administración'
admin.site.site_title = 'QA Dashboard'
admin.site.index_title = 'Panel de gestión'
