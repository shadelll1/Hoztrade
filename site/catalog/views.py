from django.http import HttpResponse


def home(request):
    return HttpResponse("Хозтрейд")


catalog_root = category = product = search = home
