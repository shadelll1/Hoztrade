from django import forms

from orders.forms import AntiSpamMixin

from .models import Review


class ReviewForm(AntiSpamMixin, forms.ModelForm):
    class Meta:
        model = Review
        fields = ["name", "rating", "text"]
        widgets = {
            "rating": forms.RadioSelect,
            "name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "text": forms.Textarea(attrs={"rows": 4, "maxlength": 2000,
                                          "placeholder": "Что понравилось, что нет, для чего покупали"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rating"].choices = [(n, str(n)) for n in range(5, 0, -1)]
        self.fields["consent"].label = "Согласен на обработку персональных данных и публикацию отзыва"

    def clean_text(self):
        text = self.cleaned_data["text"].strip()
        if len(text) < 10:
            raise forms.ValidationError("Напишите хотя бы пару слов о товаре")
        return text
