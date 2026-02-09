from django import forms
from .models import Space, Facility, SpaceType

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
            'type': forms.Select(),  # Works automatically with ForeignKey
            'location': forms.TextInput(attrs={'placeholder': 'Location'}),
            'capacity': forms.NumberInput(attrs={'placeholder': 'Capacity'}),
            'description': forms.Textarea(attrs={'placeholder': 'Describe the space...'}),
            'image': forms.FileInput(),
            'facilities': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super(SpaceForm, self).__init__(*args, **kwargs)
        # CRITICAL: Refresh the lists from DB every time the form loads.
        # This ensures newly added Types or Facilities show up instantly.
        self.fields['facilities'].queryset = Facility.objects.all()
        self.fields['type'].queryset = SpaceType.objects.all()
        
        # Optional: cleaner placeholder for the dropdown
        self.fields['type'].empty_label = "Select Venue Type"

class FacilityForm(forms.ModelForm):
    class Meta:
        model = Facility
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Projector'}),
        }