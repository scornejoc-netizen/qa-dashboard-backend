"""
Modelos del dashboard gerencial de desarrolladores.

Cada Developer tiene N Requirements asignados. Cada Requirement tiene
N TestExecution (uno por tipo de prueba: unit/integration/api/e2e).

Las métricas derivadas (weighted_quality, cycle_time_days, pass_pct) se
calculan en propiedades del modelo — no se persisten — para garantizar
que siempre reflejen el estado actual.
"""
from django.db import models


class Developer(models.Model):
    LEVEL_CHOICES = [
        ('junior', 'Junior'),
        ('mid', 'Semi Senior'),
        ('senior', 'Senior'),
    ]

    full_name = models.CharField('Nombre completo', max_length=200)
    level = models.CharField('Nivel', max_length=10, choices=LEVEL_CHOICES, default='mid')
    email = models.EmailField('Correo', blank=True)
    github_username = models.CharField('Usuario GitHub', max_length=100, blank=True)
    active = models.BooleanField('Activo', default=True)
    joined_at = models.DateField('Fecha de ingreso', null=True, blank=True)

    class Meta:
        ordering = ['full_name']
        verbose_name = 'Desarrollador'
        verbose_name_plural = 'Desarrolladores'

    def __str__(self):
        return f"{self.full_name} ({self.get_level_display()})"


class Sprint(models.Model):
    name = models.CharField('Nombre', max_length=100)
    start_date = models.DateField('Fecha inicio')
    end_date = models.DateField('Fecha fin')
    notes = models.TextField('Notas', blank=True)

    class Meta:
        ordering = ['-start_date']
        verbose_name = 'Sprint'
        verbose_name_plural = 'Sprints'

    def __str__(self):
        return self.name


class Requirement(models.Model):
    TYPE_CHOICES = [
        ('feature', 'Funcionalidad nueva'),
        ('bug', 'Corrección de bug'),
        ('tech_debt', 'Deuda técnica'),
        ('improvement', 'Mejora'),
    ]
    STATUS_CHOICES = [
        ('todo', 'Por hacer'),
        ('in_progress', 'En desarrollo'),
        ('qa', 'En QA'),
        ('done', 'Entregado'),
        ('released', 'En producción'),
    ]

    code = models.CharField(
        'Código', max_length=50, unique=True, blank=True,
        help_text='Ej: REQ-2426. Si se deja vacío, se genera automáticamente como REQ-NNN.',
    )
    title = models.CharField('Título', max_length=300)
    description = models.TextField('Descripción', blank=True)
    type = models.CharField('Tipo', max_length=20, choices=TYPE_CHOICES, default='feature')
    status = models.CharField('Estado', max_length=20, choices=STATUS_CHOICES, default='todo')
    space = models.CharField(
        'Espacio / módulo', max_length=100, blank=True,
        help_text='Módulo funcional del producto (ej: TUTOR_VIRTUAL, AGENDA_COMERCIAL_V5).',
    )

    developers = models.ManyToManyField(
        Developer,
        related_name='requirements',
        verbose_name='Desarrolladores asignados',
        help_text='Uno o más desarrolladores que trabajaron en este requerimiento.',
    )
    sprint = models.ForeignKey(
        Sprint,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='requirements',
        verbose_name='Sprint',
    )

    created_at = models.DateField('Fecha creación')
    planned_start_date = models.DateField(
        'Inicio planificado', null=True, blank=True,
        help_text='Fecha planificada de inicio (según el cronograma).',
    )
    planned_end_date = models.DateField(
        'Entrega planificada', null=True, blank=True,
        help_text='Fecha planificada de entrega (cronograma). Se compara contra la entrega real para la desviación.',
    )
    started_at = models.DateField('Inicio real', null=True, blank=True,
                                   help_text='Fecha real en que se empezó a desarrollar.')
    delivered_at = models.DateField('Entrega real', null=True, blank=True,
                                     help_text='Fecha real de entrega. Desviación = entrega real − entrega planificada.')
    closed_at = models.DateField('Fecha cierre', null=True, blank=True)

    qa_bounces = models.PositiveIntegerField('Retornos de QA', default=0,
                                              help_text='Cuántas veces volvió de QA al desarrollador.')
    production_bugs = models.PositiveIntegerField('Bugs en producción', default=0,
                                                   help_text='Bugs encontrados después del release.')
    is_documented = models.BooleanField(
        'Documentado', default=False,
        help_text='Marcar cuando exista documentación funcional/técnica del requerimiento.',
    )

    jira_url = models.URLField('URL en Jira', blank=True)
    notes = models.TextField('Notas / observaciones', blank=True)

    class Meta:
        ordering = ['-delivered_at', '-created_at']
        verbose_name = 'Requerimiento'
        verbose_name_plural = 'Requerimientos'

    def __str__(self):
        return f"{self.code} — {self.title[:60]}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._generate_next_code()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_next_code():
        """Genera el siguiente REQ-NNN basado en los códigos existentes."""
        existing = Requirement.objects.filter(code__regex=r'^REQ-\d+$').values_list('code', flat=True)
        max_num = 0
        for c in existing:
            try:
                n = int(c.split('-', 1)[1])
                if n > max_num:
                    max_num = n
            except (ValueError, IndexError):
                continue
        return f'REQ-{max_num + 1:03d}'

    @property
    def cycle_time_days(self):
        """Días desde inicio de desarrollo hasta entrega a QA."""
        if self.started_at and self.delivered_at:
            return (self.delivered_at - self.started_at).days
        return None

    @property
    def time_deviation_days(self):
        """Desviación = entrega real − entrega planificada (en días).

        Positivo = se atrasó respecto al plan. Negativo = se adelantó. 0 = a tiempo.
        None si falta alguna de las dos fechas.
        """
        if self.delivered_at and self.planned_end_date:
            return (self.delivered_at - self.planned_end_date).days
        return None

    @property
    def weighted_quality(self):
        """% ponderado de tests pasados (pasados / total) sumando todos los tipos."""
        executions = self.test_executions.all()
        total = sum(e.total for e in executions)
        passed = sum(e.passed for e in executions)
        if total == 0:
            return None
        return round(passed / total * 100, 1)

    @property
    def tests_summary(self):
        """Resumen rápido para mostrar en list_display del admin."""
        execs = self.test_executions.all()
        if not execs:
            return '—'
        total = sum(e.total for e in execs)
        passed = sum(e.passed for e in execs)
        return f"{passed}/{total}"


class TestExecution(models.Model):
    TYPE_CHOICES = [
        ('unit', 'Unitarias'),
        ('integration', 'Integración'),
        ('api', 'API'),
        ('e2e', 'End-to-End'),
    ]

    requirement = models.ForeignKey(
        Requirement,
        on_delete=models.CASCADE,
        related_name='test_executions',
        verbose_name='Requerimiento',
    )
    test_type = models.CharField('Tipo de prueba', max_length=20, choices=TYPE_CHOICES)
    total = models.PositiveIntegerField('Total pruebas')
    passed = models.PositiveIntegerField('Pasaron')
    executed_at = models.DateField('Fecha ejecución')
    notes = models.TextField('Observaciones', blank=True,
                              help_text='Ej: "Mayor fallo en validaciones de borde".')

    class Meta:
        ordering = ['requirement', 'test_type']
        verbose_name = 'Ejecución de pruebas'
        verbose_name_plural = 'Ejecuciones de pruebas'
        unique_together = ('requirement', 'test_type')

    def __str__(self):
        return f"{self.requirement.code} — {self.get_test_type_display()} ({self.passed}/{self.total})"

    @property
    def failed(self):
        return max(self.total - self.passed, 0)

    @property
    def pass_pct(self):
        if self.total == 0:
            return 0.0
        return round(self.passed / self.total * 100, 1)
