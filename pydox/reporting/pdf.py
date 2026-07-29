import sys
import pydox as do
import tempfile
from pathlib import Path
from typing import Literal, TypedDict, Optional
from dataclasses import asdict

from fpdf import FPDF, FPDF_VERSION
from fpdf.image_parsing import preload_image
from fpdf.outline import TableOfContents

from pydox.commodities import PydoxFigure

if do.get_params("reports.template") is not None:
    if do.get_params("reports.template").lower() == "lops":
        from pydox.reporting.lops import COLORS
    else:
        raise ValueError(
            f"Invalid template '{do.get_params('reports.template')}'. Valid values are: {do.get_params('reports.template_list')}"
        )
else:
    # Load default LOPS template
    from pydox.reporting.lops import COLORS


class FpdfBoundingBox(TypedDict):
    x: float
    y: float
    w: float
    h: float


def scale_and_position_image(
    pdf: FPDF,
    image_path: str,
    bounding_box: FpdfBoundingBox,
    anchor: Literal["TL", "TR", "BL", "BR", "C"],
) -> None:
    if anchor == "C":
        pdf.image(
            str(image_path),
            x=bounding_box["x"],
            y=bounding_box["y"],
            w=bounding_box["w"],
            h=bounding_box["h"],
            keep_aspect_ratio=True,
        )
        return

    info = preload_image(pdf.image_cache, str(image_path))[2]
    _, _, scaled_w, scaled_h = info.scale_inside_box(**bounding_box)

    # default to top left
    x, y = bounding_box["x"], bounding_box["y"]
    if "B" in anchor:
        y = bounding_box["y"] + bounding_box["h"] - scaled_h
    if "R" in anchor:
        x = bounding_box["x"] + bounding_box["w"] - scaled_w

    pdf.image(
        str(image_path),
        x=x,
        y=y,
        w=scaled_w,
        h=scaled_h,
        keep_aspect_ratio=True,
    )


def registry_report(
    registry,
    outputfile: Path | str,
    tocpage: bool = True,
    sort_by: Optional[str] = None,
    **kwargs,
):
    outputfile = Path(outputfile)

    class PDF(FPDF):
        def reset_font(self):
            self.set_font("helvetica", size=12)

        def header(self):
            # Setting font: helvetica bold 15
            self.set_font("helvetica", style="B", size=15)
            # Calculating width of title and setting cursor position:
            width = self.get_string_width(self.title) + 6
            self.set_x((210 - width) / 2)
            # self.set_y(0)

            # Setting thickness of the frame (1 mm)
            self.set_line_width(1)

            # Printing title:
            self.cell(
                width,
                10,
                self.title,
                border=1,
                new_x="LMARGIN",
                new_y="NEXT",
                align="C",
                fill=True,
            )
            # Performing a line break:
            self.ln(10)
            self.reset_font()

        def footer(self):
            # Setting position at 1.5 cm from bottom:
            self.set_y(-15)
            # Setting font: helvetica italic 8
            self.set_font("helvetica", style="I", size=8)
            # self.set_text_color(*[int(c*255) for c in COLORS.MEDIUM_DARK[0:-1]])
            # Printing page number
            # self.cell(0, 10, f"Page {self.page_no()}", align="C")
            self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")
            self.reset_font()

        def figure_title(self, pfig: PydoxFigure):
            # Setting font: helvetica 12
            self.set_font("helvetica", size=14)
            # Printing chapter name:
            self.cell(
                0,
                6,
                f"**Name: {pfig.name}**",
                markdown=True,
                new_x="LMARGIN",
                new_y="NEXT",
                align="L",
                fill=True,
            )
            self.set_font("helvetica", size=12)
            self.cell(
                0,
                6,
                f"Category: {pfig.category} (level={pfig.level})",
                markdown=True,
                new_x="LMARGIN",
                new_y="TOP",
                # new_y="NEXT",
                align="L",
                fill=False,
            )
            self.set_font("courier", size=9)
            width = (
                self.get_string_width(f"Category: {pfig.category} (level={pfig.level})")
                + 6
            )
            # self.set_x((210 - width) / 2)
            uid = "\n-".join(str(pfig.config_uid).split("-"))
            self.multi_cell(
                0,
                6,
                f"UID: {uid}",
                markdown=False,
                new_x="LMARGIN",
                new_y="NEXT",
                align="R",
                fill=False,
                max_line_height=3,
            )
            # Performing a line break:
            self.ln(4)
            self.reset_font()

    pdf = PDF(orientation="portrait", format="A4")
    pdf.oversized_images = "WARN"
    pdf.set_margin(10)
    pdf.set_auto_page_break(auto=True)
    pdf.set_lang("en-US")
    pdf.set_author([do.get_params("operator.name")])
    pdf.set_subject(kwargs.get("subject", "Pydox report"))
    pdf.set_producer(
        "Python/{0[0]}.{0[1]} py-pdf/fpdf2/{1}".format(sys.version_info, FPDF_VERSION)
    )
    pdf.set_creator(f"Pydox/{do.__version__} (+https://github.com/euroargodev/pydox)")

    # Setting colors for frame, background and text:
    pdf.set_draw_color(
        *[int(c * 255) for c in COLORS.MEDIUM[0:-1]]
    )  # Defines the color used for all stroking operations (lines, rectangles and cell borders)
    pdf.set_fill_color(
        *[int(c * 255) for c in COLORS.LIGHTEST[0:-1]]
    )  # Defines the color used for all filling operations (filled rectangles and cell backgrounds)
    pdf.set_text_color(
        *[int(c * 255) for c in COLORS.DARK[0:-1]]
    )  # Defines the color used for text

    pdf.set_title(kwargs.get("title", "Pydox figures registry"))

    if tocpage:
        pdf.add_page()
        pdf.set_y(50)
        pdf.set_font("helvetica", size=12)
        toc = TableOfContents()
        pdf.insert_toc_placeholder(toc.render_toc, allow_extra_pages=True)

    sort_by = sort_by if sort_by is not None else "category"
    if sort_by == "category":
        subsection = "name"
    elif sort_by == "name":
        subsection = "category"
    elif sort_by == "config_uid":
        subsection = "category"

    sort_values = set([asdict(f)[sort_by] for f in registry])
    sorted_content = {}
    for val in sort_values:
        sorted_content[val]: list[PydoxFigure] = []
    for f in registry:
        val = asdict(f)[sort_by]
        sorted_content[val].append(f)

    for section, figures in sorted_content.items():
        section_open = False

        for pfig in figures:
            pdf.add_page()
            if not section_open:
                pdf.start_section(name=f"{sort_by.title()}: '{section}'", level=0)
                section_open = True
            pdf.start_section(name=asdict(pfig)[subsection], level=1)
            pdf.figure_title(pfig)

            with tempfile.NamedTemporaryFile(mode="w+b") as f:
                png_file = Path(f.name).with_suffix(".png")
                pfig.fig.savefig(png_file)

                sx, sy = 0.9, 1
                bounding_box = FpdfBoundingBox(
                    x=(1 - sx) * pdf.w / 2,
                    w=sx * pdf.w,
                    y=pdf.get_y(),
                    h=sy * (pdf.h - pdf.get_y() - 15),
                )  # 15 is the footer height

                # Render the bounding box:
                if kwargs.get("debug", False):
                    pdf.rect(**bounding_box, style="D")

                # Insert image:
                # scale_and_position_image(pdf, png_file, bounding_box, "C")
                pdf.image(
                    str(png_file),
                    x=bounding_box["x"],
                    y=bounding_box["y"],
                    w=bounding_box["w"],
                    h=bounding_box["h"],
                    keep_aspect_ratio=True,
                )

    # Final export to a PDF file:
    pdf.output(outputfile)
    return outputfile
