"""Validated narrated render geometry; historical portrait/landscape stay exact."""
from .contracts import WorkflowError
from .north_star_quality import validate_render_profile


def layout(profile,width,height,ratio,brand,*,editable):
    validate_render_profile(profile,width,height,ratio)
    safe=brand.safe_areas
    if profile in ('vertical-short','landscape'):
        landscape=profile=='landscape'
        left,right,top,bottom=(90,90,55,100) if landscape else (safe.left,safe.right,safe.top,safe.bottom)
        return {'safe_left':left,'safe_right':right,'safe_top':top,'safe_bottom':bottom,
            'media_top':230 if landscape else 390,'plane_height':530 if landscape else 830 if editable else 1000,
            'caption_top':850 if landscape else 1320,'title_font_size':52 if landscape else 60,
            'subtitle_font_size':38 if landscape else brand.subtitle_style.font_size,'label_font_size':24 if landscape else 28,
            'illustration_y':775 if landscape else 1215 if editable else 1390,'footer_y':810 if landscape else 1250}
    if not editable:raise WorkflowError('NARRATED_COMPACT_CANVAS_REQUIRES_EDIT_PLAN',400)
    square=profile=='square';top=round(safe.top*(.4 if square else .55));bottom=round(safe.bottom*(.45 if square else .65))
    caption_top=height-bottom-110;footer_y=caption_top-68;illustration_y=footer_y-36
    media_top=270 if square else 310;plane_height=(illustration_y-18-media_top)//2*2
    subtitle_size=min(brand.subtitle_style.font_size,38 if square else 42)
    if plane_height<320 or caption_top<=media_top+plane_height or height-bottom-caption_top<subtitle_size*2+12:
        raise WorkflowError('NARRATED_CANVAS_SAFE_LAYOUT_INVALID',400)
    return {'safe_left':safe.left,'safe_right':safe.right,'safe_top':top,'safe_bottom':bottom,
        'media_top':media_top,'plane_height':plane_height,'caption_top':caption_top,'title_font_size':46 if square else 52,
        'subtitle_font_size':subtitle_size,'label_font_size':24,'illustration_y':illustration_y,'footer_y':footer_y}
