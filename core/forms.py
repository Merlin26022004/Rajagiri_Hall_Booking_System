from django import forms
from django.core.exceptions import ValidationError
from .models import Space, Facility, SpaceType, Booking

# === NEW FORM: For adding Venue Types (e.g. Auditorium) ===
class SpaceTypeForm(forms.ModelForm):
    class Meta:
        model = SpaceType
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Seminar Hall'}),
        }

class SpaceForm(forms.ModelForm):
    class Meta:
        model = Space
        fields = ['name', 'type', 'location', 'capacity', 'description', 'image', 'facilities']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Name'}),
            'type': forms.Select(),
            'location': forms.TextInput(attrs={'placeholder': 'Location'}),
            'capacity': forms.NumberInput(attrs={'placeholder': 'Capacity'}),
            'description': forms.Textarea(attrs={'placeholder': 'Describe the space...'}),
            'image': forms.FileInput(),
            'facilities': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super(SpaceForm, self).__init__(*args, **kwargs)
        self.fields['facilities'].queryset = Facility.objects.all()
        self.fields['type'].queryset = SpaceType.objects.all()
        self.fields['type'].empty_label = "Select Venue Type"

class FacilityForm(forms.ModelForm):
    class Meta:
        model = Facility
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Projector'}),
        }

# ==========================================
# === NEW BOOKING FORMS (Feature 1 & 3) ===
# ==========================================

class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = [
            'space', 'date', 'start_time', 'end_time', 
            'purpose', 'expected_count', 'faculty_in_charge',
            'resource_type', 'resource_name', 'resource_number', # <--- Priority Fields
            'requested_facilities'
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'purpose': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Event details...'}),
            'requested_facilities': forms.CheckboxSelectMultiple(),
            
            # Add IDs to these fields so we can toggle them with JavaScript
            'resource_type': forms.Select(attrs={'id': 'id_resource_type', 'class': 'form-select'}),
            'resource_name': forms.TextInput(attrs={'id': 'id_resource_name', 'placeholder': 'Dignitary Name'}),
            'resource_number': forms.TextInput(attrs={'id': 'id_resource_number', 'placeholder': 'Contact Number'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_time')
        end = cleaned_data.get('end_time')
        r_type = cleaned_data.get('resource_type')
        r_name = cleaned_data.get('resource_name')
        r_num = cleaned_data.get('resource_number')

        # 1. Basic Time Validation
        if start and end and start >= end:
            raise ValidationError("End time must be after start time.")

        # 2. Conditional Validation for "External" Priority
        # If user selects External, they MUST provide details.
        if r_type == Booking.RESOURCE_EXTERNAL:
            if not r_name:
                self.add_error('resource_name', "Resource Name is required for External events.")
            if not r_num:
                self.add_error('resource_number', "Contact Number is required for External events.")

        return cleaned_data

class RescheduleForm(forms.ModelForm):
    """
    Simplified form for Feature 3: Easy Rescheduling.
    Only allows editing time and date.
    """
    class Meta:
        model = Booking
        fields = ['date', 'start_time', 'end_time']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_time')
        end = cleaned_data.get('end_time')

        if start and end and start >= end:
            raise ValidationError("End time must be after start time.")
        
        return cleaned_data