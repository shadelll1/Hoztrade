from django.shortcuts import render

from .services import calc_data, tariff_table


def delivery_page(request):
    """Условия доставки: автопарк, тарифы по зонам и калькулятор по весу."""
    trucks, rows = tariff_table()
    calc = calc_data((trucks, rows))
    return render(request, "pages/delivery.html", {"trucks": trucks, "rows": rows, "calc": calc})
