from .permissions import is_site_admin


def access_control(request):
    return {"is_site_admin": is_site_admin(request.user)}
