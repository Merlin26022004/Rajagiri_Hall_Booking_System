from django import forms
from .models import Space, Facility

class SpaceForm(forms.ModelForm):
    class Meta:
        model = Space
        # Added 'managed_by' if you still want Faculty to assign owners
        fields = ['name', 'type', 'location', 'capacity', 'description', 'image', 'facilities']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Name'}),
            'type': forms.Select(),
            'location': forms.TextInput(attrs={'placeholder': 'Location'}),
            'capacity': forms.NumberInput(attrs={'placeholder': 'Capacity'}),
            'description': forms.Textarea(attrs={'placeholder': 'Describe the space...'}),
            'image': forms.FileInput(),
            # This ensures the loop in manage_resources.html works
            'facilities': forms.CheckboxSelectMultiple(),
        }

class FacilityForm(forms.ModelForm):
    class Meta:
        model = Facility
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Projector'}),
        }