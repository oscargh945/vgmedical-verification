from uuid import uuid4

# Core Django imports
from django.db.models import BooleanField
from django.db.models import UUIDField

# Third party imports
from model_utils.models import SoftDeletableModel
from model_utils.models import TimeStampedModel


class BaseModel(TimeStampedModel, SoftDeletableModel):
    """
    Base Model
    """

    id = UUIDField(primary_key=True, default=uuid4, editable=False)
    is_active = BooleanField(default=True)

    class Meta:
        abstract = True
