from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import Q

class Timestamped(models.Model):
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        abstract = True

class Review(Timestamped):
    is_demo = models.BooleanField(default=False, db_index=True)
    demo_key = models.CharField(max_length=64, unique=True, null=True, blank=True)
    name = models.CharField(max_length=255)
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    review = models.TextField()
    status = models.CharField(max_length=10, choices=[(s,s) for s in ('pending','approved','rejected')], default='pending', db_index=True)
    class Meta:
        db_table = 'reviews'
        ordering = ['-created_at', '-id']
        constraints = [models.CheckConstraint(condition=Q(rating__gte=1, rating__lte=5), name='review_rating_range'),
                       models.CheckConstraint(condition=Q(status__in=['pending','approved','rejected']), name='review_status_valid')]

class ContactRequest(Timestamped):
    class Status(models.TextChoices):
        NEW = 'new', 'جديد'
        IN_PROGRESS = 'in_progress', 'قيد المراجعة'
        CONTACTED = 'contacted', 'تم التواصل'
        CLOSED = 'closed', 'مغلق'

    class Type(models.TextChoices):
        CONSULTATION = 'consultation', 'استشارة'
        CONTACT = 'contact', 'تواصل'

    request_type = models.CharField(max_length=12, choices=Type.choices, default=Type.CONSULTATION, db_index=True)
    internal_notes = models.TextField(blank=True)
    is_demo = models.BooleanField(default=False, db_index=True)
    demo_key = models.CharField(max_length=64, unique=True, null=True, blank=True)
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=30)
    email = models.EmailField(max_length=255, null=True, blank=True)
    service = models.CharField(max_length=255)
    message = models.TextField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW, db_index=True)
    class Meta:
        db_table = 'contact_requests'
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['request_type', '-created_at'], name='request_type_created_idx')]
        constraints = [models.CheckConstraint(condition=Q(status__in=['new','in_progress','contacted','closed']), name='contact_status_valid'),
                       models.CheckConstraint(condition=Q(request_type__in=['consultation','contact']), name='request_type_valid')]

class SubmissionReceipt(models.Model):
    """Short-lived HMAC fingerprint, containing no raw client data."""
    key = models.CharField(max_length=64, primary_key=True)
    expires_at = models.DateTimeField(db_index=True)

class SubmissionWindow(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    started_at = models.DateTimeField()
    count = models.PositiveIntegerField(default=1)
