# -*- coding: utf-8 -*-
def classFactory(iface):
    from .geometry_extractor import GeometryExtractorPlugin
    return GeometryExtractorPlugin(iface)
