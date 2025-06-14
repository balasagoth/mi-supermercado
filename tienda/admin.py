import csv
from django.contrib import admin
from django.http import HttpResponse
from django.utils.html import format_html
from .models import DisenoPersonalizado, Categoria, Producto, Pedido, DetallePedido

# ==============================================================================
# ACCIONES PERSONALIZADAS PARA EL ADMIN
# Estas funciones se pueden aplicar a un conjunto de objetos seleccionados.
# ==============================================================================

@admin.action(description="Exportar seleccionados a CSV/Excel")
def exportar_a_csv(modeladmin, request, queryset):
    """
    Acción que exporta los pedidos seleccionados a un archivo CSV.
    """
    meta = modeladmin.model._meta
    field_names = [field.name for field in meta.fields]

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename={meta.verbose_name_plural}.csv'
    writer = csv.writer(response)

    writer.writerow(field_names)
    for obj in queryset:
        row = writer.writerow([getattr(obj, field) for field in field_names])

    return response


@admin.action(description="Marcar productos como DISPONIBLES")
def marcar_como_disponible(modeladmin, request, queryset):
    """
    Acción para poner masivamente productos como disponibles.
    """
    queryset.update(disponible=True)


@admin.action(description="Marcar productos como NO DISPONIBLES")
def marcar_como_no_disponible(modeladmin, request, queryset):
    """
    Acción para ocultar masivamente productos de la tienda.
    """
    queryset.update(disponible=False)


# ==============================================================================
# CONFIGURACIÓN DEL PANEL DE ADMINISTRADOR PARA CADA MODELO
# ==============================================================================

@admin.register(DisenoPersonalizado)
class DisenoPersonalizadoAdmin(admin.ModelAdmin):
    """
    Administración del modelo de Personalización de Diseño.
    """
    list_display = ('color_primario', 'fuente_principal', 'logo', 'banner_principal')

    # Limita a que solo pueda existir una única fila de configuración.
    def has_add_permission(self, request):
        return DisenoPersonalizado.objects.count() == 0

    def has_delete_permission(self, request, obj=None):
        # Evita que se pueda borrar la configuración, solo se puede editar.
        return False


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    """
    Administración del modelo de Categorías.
    """
    list_display = ('nombre', 'descripcion')
    search_fields = ('nombre',)


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    """
    Administración del modelo de Productos, con muchas mejoras de usabilidad.
    """
    list_display = ('imagen_tag', 'nombre', 'categoria', 'precio', 'stock', 'disponible')
    list_filter = ('categoria', 'disponible', 'fecha_ingreso')
    search_fields = ('nombre', 'descripcion', 'categoria__nombre')
    
    # Permite editar estos campos directamente desde la lista, sin entrar al detalle.
    list_editable = ('precio', 'stock', 'disponible')
    
    # Acciones personalizadas que aparecerán en el menú desplegable "Acciones".
    actions = [exportar_a_csv, marcar_como_disponible, marcar_como_no_disponible]

    # Campo para previsualizar la imagen en la lista de productos
    @admin.display(description='Imagen')
    def imagen_tag(self, obj):
        if obj.imagen:
            return format_html('<img src="{}" width="50" height="50" style="object-fit: cover;" />', obj.imagen.url)
        return "No Imagen"


class DetallePedidoInline(admin.TabularInline):
    """
    Permite ver y editar los detalles de un pedido (los productos)
    directamente dentro de la vista de detalle de un Pedido.
    """
    model = DetallePedido
    extra = 0  # No mostrar filas vacías para añadir nuevos ítems.
    readonly_fields = ('producto', 'cantidad', 'precio_unitario', 'subtotal')
    
    # Campo calculado para mostrar el subtotal de cada línea.
    @admin.display(description='Subtotal')
    def subtotal(self, obj):
        return f"${obj.get_subtotal()}"

    # No permitir añadir o borrar detalles de un pedido ya creado desde el admin.
    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    """
    Administración del modelo de Pedidos.
    """
    list_display = ('id', 'usuario', 'fecha_pedido', 'estado', 'total', 'id_transaccion_pago')
    list_filter = ('estado', 'fecha_pedido', 'usuario')
    search_fields = ('usuario__username', 'id', 'id_transaccion_pago')
    date_hierarchy = 'fecha_pedido'  # Añade una navegación por fechas en la parte superior.
    
    # Los pedidos no se deberían poder crear o modificar libremente desde el admin.
    # Son generados por el sistema de pago. Solo se debería poder cambiar el estado.
    readonly_fields = ('usuario', 'fecha_pedido', 'total', 'id_transaccion_pago')
    
    # Se integra el "Inline" para ver los productos del pedido.
    inlines = [DetallePedidoInline]
    
    # Acción de exportación.
    actions = [exportar_a_csv]

    # Solo permitir editar el estado y la dirección de envío
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj: # Si el objeto ya existe (no es un nuevo pedido)
            form.base_fields['estado'].disabled = False
            form.base_fields['direccion_envio'].disabled = False
        return form


# Opcional: registrar los modelos que no tienen una clase Admin personalizada
# admin.site.register(DetallePedido) # No es necesario si se usa como Inline

# Cambiar el título principal del panel de administración
admin.site.site_header = "Panel de Administración del Supermercado"
admin.site.site_title = "Admin Supermercado"
admin.site.index_title = "Bienvenido al gestor de la tienda"
