from django.shortcuts import render

from .services import tariff_table


def delivery_page(request):
    """Условия доставки: автопарк, тарифы по зонам и калькулятор по весу."""
    trucks, rows = tariff_table()
    calc = {
        "trucks": [{"name": t.name, "kg": float(t.capacity_kg)} for t in trucks],
        "zones": [{"name": z.name, "prices": [float(p) if p is not None else None for p in prices]}
                  for z, prices in rows],
    }
    return render(request, "pages/delivery.html", {"trucks": trucks, "rows": rows, "calc": calc})
