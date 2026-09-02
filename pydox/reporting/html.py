import re
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from copy import deepcopy
import argopy as ar
import importlib
import pandas as pd
from typing import Dict, Any

import pydox as do
from pydox.commodities import PydoxFigure
from pydox.reporting.logs import getLogger

log = getLogger("pydox.reporting.html", context_level=10)

_path2static = Path(
    importlib.util.find_spec("pydox.static").submodule_search_locations[0]
)

slug = lambda name: re.sub(r"[/\\?%*:|\"<>\x7F\x00-\x1F]", "-", name)


def remove_duplicate(
    figlist: list[PydoxFigure],
) -> list[PydoxFigure]:
    """Remove duplicates based on title and 2nd part of uid"""
    seen = set()
    new_l = []
    for d in figlist:
        t = tuple([d["title"], d["uid"].split("-")[-1]])
        if t not in seen:
            seen.add(t)
            new_l.append(d)

    return new_l


html_default_summary = """
                <p>
                    In this section, write a brief description of all decisions made in DMQC analysis. 
                    You may include information about sea surface pressure corrections with applied QC flags and errors (if applicable), 
                    cell thermal mass corrections (if applicable), a decision made on salinity data including QC flags and corrections applied to salinity data (if needed).
                </p>
                <p class="example">
                    For Example:<br>
                    "The sea surface pressure in Apex float was adjusted in d-mode. For cycles 1-155, the QC=1 and error 2.4 dbar was assigned to pressure data. 
                    Cell thermal mass correction was applied. For cycles 1-155, the salty offset was detected. Correction of -0.0125 offset was applied, QC=1, error=0.005."
                </p>
"""
html_default_introduction = """
        <p>
            This would be an introduction to the report. You may include information about the float deployment context, sensor history or whatever relevant information
            with regard to the DMQC process for this float.
        </p>
"""
html_default_comment = """
        <p>
            Write comments about any problems with float and decision made on this float including e.g.
            Is the float still active? Where is float located and what is the trajectory over its lifetime? 
            Has it crossed through different water masses, changed latitude, etc? Is the float on the grey list? 
            If DMQC has been done on some profiles before what decisions have been made and if anything has changed? 
            What was the setup used in set_calseries.m? Did you run any more code iterations with different configurations? 
            If yes how it helped you to make a final decision?
        </p>
        <p class="example">
            For example:<br>
            "Float was deployed in the Brazil Basin. For most of life, this float stayed in the system of local eddies. 
            The most favourable water masses, which are useful for comparison with climatology is relatively stable 
            intermediate waters from around 400-900 m. The initial comparison between Argo float data reference data 
            from CTD data shows that salinity data are within its variability, however, slightly shifted toward saltier 
            values of CTD data. The sea surface pressure data are not displaying values below 0 dbar, however, 
            there are no indications of negative pressure drift.
            <br><br>
            The comparison with satellite altimeter data suggested some potential offset between the sea surface height 
            and dynamic height anomaly, which were further verified by comparing Argo data with Argo reference data using 
            the OWC method. This float was not DMQC-ed before. In set_calseries.m we set the maximum of barks to -1 to show 
            evidence of suspected offset. The CTD referenced data were too limited and too variable to detect any offset. 
            Much clearer result was obtained by comparing Argo float data to Argo reference data. 
            The OWC analysis showed indications of salty offset. Argo data from this float are of around 0.0125 saltier 
            that reference data. The offset of -0.0125 was applied to salinity data and submitted to GDAC. 
            This float is still active and further monitoring is still required."
        </p>
"""


class CalibrationHTMLReport:
    """HTML report generator for Calibration instances"""

    def __init__(self, c, a_float):
        self.c = c
        self.af = a_float
        self._cfg = c._cfg

        # Define standard folders for this float output:

        # <output.root>/<WMO>
        root = Path(do.get_params("output.root", config=self._cfg)).joinpath(
            f"{a_float.WMO}"
        )
        root.mkdir(parents=True, exist_ok=True)

        # Folder for figures:
        # <output.root>/<WMO>/<plots.save.path>/
        froot = root.joinpath(do.get_params("plots.save.path", config=self._cfg))
        froot.mkdir(parents=True, exist_ok=True)
        self.froot: Path = froot

        # Folder for reports:
        # <output.root>/<WMO>/<reports.save.path>/
        rroot = root.joinpath(do.get_params("reports.save.path", config=self._cfg))
        rroot.mkdir(parents=True, exist_ok=True)
        self.rroot: Path = rroot

        # Temporary folder (for anything):
        # (created automatically by pydox)
        tmp_root = do.get_params("output._tmp", config=self._cfg)
        self.tmp_root = tmp_root

    def fpath(self, figure_name: str) -> Path:
        """Absolute figure path maker
        Based on: `<output.root>/<WMO>/<plots.save.path>/{figure_name}.<plots.save.format>`
        """
        """This may be in Calibration rather than CalibrationReport"""
        return self.froot.joinpath(slug(figure_name)).with_suffix(
            f".{do.get_params('plots.save.format', config=self._cfg)}"
        )

    def relfpath(self, figure_name: str) -> Path:
        """Relative figure path maker

        (to render the Jinja2 html template, image paths must be relative to the html document)
        """
        """This may be in Calibration rather than CalibrationReport"""
        return self.fpath(figure_name).relative_to(self.rroot)

    def rpath(self, report_name: str) -> Path:
        """Report path maker

        Based on: `<output.root>/<WMO>/<reports.save.path>/<reports.save.prefix>{report_name}.<reports.save.format>`
        """
        pref = do.get_params("reports.save.prefix", config=self._cfg)
        if pref is None:
            return self.rroot.joinpath(slug(report_name)).with_suffix(
                f".{do.get_params('reports.save.format', config=self._cfg)}"
            )
        else:
            return self.rroot.joinpath(f"{pref}{slug(report_name)}").with_suffix(
                f".{do.get_params('reports.save.format', config=self._cfg)}"
            )

    def save_figures(self):
        """Save all Fitted Calibration figures

        Based on: `<output.root>/<WMO>/<plots.save.path>/{figure_name}.<plots.save.format>`

        This method may be in Calibration rather than CalibrationHTMLReport
        """

        # Save figures from the ArgoFloat instance:
        f = [f for f in do.figures if f.name == "Float trajectory"][0]
        f.fig.savefig(self.fpath(f.name), bbox_inches="tight")

        # Save figures from the Calibration instance:
        for f in self.c.figures:
            log.info("Saving Figure >", f.name)
            f.fig.savefig(
                self.fpath(f.name), bbox_inches="tight"
            )  # rq: dpi is from the fig object already

        for icfg in range(self.c.n_configs):
            for f in self.c.configs_figures[icfg]:
                log.info("Saving Figure >", f.name)
                f.fig.savefig(
                    self.fpath(f.name), bbox_inches="tight"
                )  # rq: dpi is from the fig object already

    def pydoxfig2templatefig(self, f: PydoxFigure) -> Dict[str, Any]:
        return {
            "title": f.name,
            "category": f.category,
            "legend": f.legend if f.legend is not None else f.name,
            "uid": f.config_uid,
            "src": str(self.relfpath(f.name)),  # Relative paths
            # 'src': str(fpath(f.name)), # Absolute paths
        }

    def retrieve_figlist(self, sort_by: str = "category") -> Dict[str, Dict[str, Any]]:
        """Get all :class:`PydoxFigure` objects to include in the appendix figure sections"""
        sort_values = set([getattr(f, sort_by) for f in self.c.figures])
        s2 = set(
            [
                getattr(f, sort_by)
                for icfg in range(self.c.n_configs)
                for f in self.c.configs_figures[icfg]
            ]
        )
        sort_values.update(s2)

        sorted_content = {}
        for val in sort_values:
            sorted_content[val]: list[PydoxFigure] = []

        for f in self.c.figures:
            fobj = self.pydoxfig2templatefig(f)
            sorted_content[getattr(f, sort_by)].append(fobj)

        for icfg in range(self.c.n_configs):
            for f in self.c.configs_figures[icfg]:
                fobj = self.pydoxfig2templatefig(f)
                sorted_content[getattr(f, sort_by)].append(fobj)

        return sorted_content

    def publish(self, file_name: Optional[str] = None, **kwargs) -> Path:
        """Publish an HTML report file based on the template defined in settings

        Customizable fields to be provided with kwargs:
        - 'summary'
        - 'introduction'
        - 'comment'

        Returns
        -------
        :class:`pathlib.Path`
            Following the convention: `<output.root>/<WMO>/<reports.save.path>/<reports.save.prefix>{report_name}.<reports.save.format>`
        """

        #############
        # Produce and retrieve data for the report
        #############
        self.save_figures()

        # Get PydoxFigure for: Float trajectory
        f_traj = next(
            f for f in do.figures if f.config_uid == f"{self.af.WMO}_trajectory_map"
        )
        f_traj = self.pydoxfig2templatefig(f_traj)

        # Get PydoxFigure(s) for: Best fit result (selected by user)
        for f in self.c.figures:
            # This check must be consistant with name given to the figure by: do.calibration.methods.<method>.plots.plot_fit_results_figure()
            if (
                f.name
                == f"Calibration results [configs_layout='figure', iset='{self.c.best_fit}']"
            ):
                f_plot_result = deepcopy(f)
                f_plot_result.legend = f"Calibration results obtained with configuration number {self.c.best_fit} (selected)"
                f_plot_result = self.pydoxfig2templatefig(f_plot_result)
                f_plot_result["title"] = f_plot_result["title"].split("[")[0]
                f_plot_result["title"] = f_plot_result["title"].strip()

        # Get all PydoxFigure objects to include in the appendix figure sections:
        sorted_content = self.retrieve_figlist(sort_by="category")

        # Some figures are generated with a 2nd uid component based on input parameters (eg: get_argo_data_for_in_air_method)
        # This allows to identify figures generated with similar low-level data even from different high level object.
        # So we can remove duplicates based on title and this 2nd part of uid:
        for key in sorted_content.keys():
            sorted_content[key] = remove_duplicate(sorted_content[key])

        #############
        # Retrieve the HTML template and format data to fill it
        #############

        # Get the template file:
        template_name = do.get_params("reports.template", config=self._cfg)
        html_template_file = Path(
            do.get_params(f"reports.templates.{template_name}.html"), config=self._cfg
        )

        if template_name == "pydox":
            # Make file path absolute for internal Pydox templates:
            html_template_file = _path2static.joinpath("templates").joinpath(
                html_template_file
            )

        # loader = FileSystemLoader(Path().cwd()) # from a relative file path
        loader = FileSystemLoader(
            str(html_template_file.parent)
        )  # from an absolute file path
        template = Environment(loader=loader).get_template(html_template_file.name)

        # Define template data, because they depend on the template model:
        # (ie needs to be adapted to the template file)
        template_kwargs = {
            "operator": do.get_params("operator", config=self._cfg),
            "af": self.af,
            "fleetmonitoring_url": ar.dashboard(wmo=self.af.WMO, url_only=True),
            "iselected": self.c.best_fit,
            "plot_traj": f_traj,
            "plot_result": f_plot_result,
            "figures": sorted_content,
        }

        # Fill in template data with specific user input:
        for key in kwargs:
            template_kwargs.update({key: kwargs[key]})

        # Fill in template data with mandatory, but still missing, information:
        # (we also use default values to help users)
        if "WMO" not in template_kwargs:
            template_kwargs["WMO"] = self.af.WMO

        if "summary" not in template_kwargs:
            template_kwargs["summary"] = html_default_summary

        if "introduction" not in template_kwargs:
            template_kwargs["introduction"] = html_default_introduction

        if "comment" not in template_kwargs:
            template_kwargs["comment"] = html_default_comment

        if "creation_date" not in template_kwargs:
            template_kwargs["creation_date"] = pd.to_datetime(
                "now", utc=False
            ).isoformat(timespec="seconds")

        if "creator" not in template_kwargs:
            template_kwargs["creator"] = (
                f"Pydox/{do.__version__} (+https://github.com/euroargodev/pydox) using template named='{do.get_params('reports.template', config=self._cfg)}'"
            )

        if "colors" not in template_kwargs:
            template_kwargs["colors"] = do.reporting.COLORS.SCHEME

        template_kwargs["icon_orcid"] = _path2static.joinpath("img/orcid_icon.png")
        template_kwargs["logo_pydox"] = _path2static.joinpath(
            "img/pydox-logo-long-800.png"
        )

        #############
        # Finally render the template
        #############
        html = template.render(**template_kwargs)
        file_name: str = (
            "preliminary_report"
            if file_name is None
            else file_name.removesuffix(".html")
        )
        report_file = self.rpath(file_name)
        with open(report_file, "w") as f:
            f.write(html)

        log.info(f"HTML report saved to: {report_file}")

        return report_file
