def contexto_inicio(usuario):
    from actualizaciones.servicios import aviso_para
    from banco.conciliacion import cambios_de_topes_ajenos

    contexto = {"aviso_actualizacion": aviso_para(usuario)}
    if usuario.tiene_permiso("ver_auditoria"):
        contexto["cambios_topes"] = cambios_de_topes_ajenos(usuario)
    return contexto
