def classFactory(iface):
    from .check_a_kea import CheckAKea
    return CheckAKea(iface)