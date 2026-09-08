import re
from pathlib import Path
import shutil
from jinja2 import Environment, FileSystemLoader
from copy import deepcopy
import argopy as ar
import importlib
import pandas as pd
from typing import Dict, Optional, TypeAlias

import pydox as do
from pydox.commodities import PydoxFigure
from pydox.reporting.logs import getLogger

log = getLogger("pydox.reporting.html", context_level=10)

_path2static = Path(
    importlib.util.find_spec("pydox.static").submodule_search_locations[0]
)

slug = lambda name: re.sub(r"[/\\?%*:|\"<>\x7F\x00-\x1F]", "-", name)

TemplateFigure: TypeAlias = Dict[str, str]
"""A type to describe what is sent to the template to represent one figure, typically based on a PydoxFigure instance"""


def remove_duplicate(
    figlist: list[TemplateFigure],
) -> list[TemplateFigure]:
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
        <p class="example">
            For example:<br>            
            Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.
        </p>
"""
html_default_discussion = """
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


class FloatPathMaker:
    def __init__(self, fitted_c, include_static: bool = True):
        if not fitted_c.fitted:
            raise ValueError("A PathMaker requires a fitted Calibration instance")

        self._cfg = fitted_c._cfg
        self.WMO = fitted_c._fitted_float["WMO"]

        # Define and create standard folders for this float:

        # <output.root>/<WMO>
        self.root: Path = Path(do.get_params("output.root", config=self._cfg)).joinpath(
            f"{self.WMO}"
        )
        self.root.mkdir(parents=True, exist_ok=True)

        # Folder for figures:
        # <output.root>/<WMO>/<plots.save.path>/
        self.froot: Path = self.root.joinpath(
            do.get_params("plots.save.path", config=self._cfg)
        )
        self.froot.mkdir(parents=True, exist_ok=True)

        # Folder for reports:
        # <output.root>/<WMO>/<reports.save.path>/
        self.rroot: Path = self.root.joinpath(
            do.get_params("reports.save.path", config=self._cfg)
        )
        self.rroot.mkdir(parents=True, exist_ok=True)
        if include_static:
            # <output.root>/<WMO>/<reports.save.path>/static/img
            self.rroot_img = self.rroot.joinpath("static").joinpath("img")
            self.rroot_img.mkdir(parents=True, exist_ok=True)

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

        (to render the Jinja2 HTML template, image paths must be relative to the html document)
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


class CalibrationHTMLReport:
    """HTML report generator for fitted Calibration instances"""

    def __init__(self, c: "Calibration", a_float: ar.ArgoFloat, **kwargs):
        if not c.fitted:
            raise ValueError(
                "A CalibrationHTMLReport requires a fitted Calibration instance"
            )
        if c._fitted_float["WMO"] != a_float.WMO:
            raise ValueError(
                f"Cannot create a HTML report for this float ({a_float.WMO}) because it is not the same used to fit this calibration ({c._fitted_float['WMO']})"
            )

        self.c = c
        self._cfg = kwargs.get(
            "config", c._cfg
        )  # Possibly overwrite the configuration to use, primarily used for debug
        self.af = a_float
        self.pm = FloatPathMaker(c)

    def plot_float_traj(self):
        fig, ax, ptch = self.af.plot.trajectory(cbar=False)
        return do.figures.commit(
            fig,
            name="Float trajectory",
            config_uid=f"{self.af.WMO}_trajectory_map",
            watermark="Argopy",
        )

    def save_static(self):
        """Save Pydox template static figures required from the template

        Copying static figures to the report path allows for figures to be inserted with relative paths.
        """
        # Copy all static.templates.img/*.png
        src = _path2static.joinpath("templates").joinpath("img")
        dst = self.pm.rroot.joinpath("static").joinpath("img")
        shutil.copytree(src, dst, dirs_exist_ok=True)

    def _save_figure(self, f):
        if self.pm.fpath(f.name).exists():
            log.warning(f"Saving Figure '{f.name}' (⚠️ overwrite)")
        else:
            log.info(f"Saving Figure '{f.name}'")
        f.fig.savefig(
            self.pm.fpath(f.name), bbox_inches="tight"
        )  # rq: dpi is from the fig object already

    def save_figures(self):
        """Save all Fitted Calibration figures

        Based on: `<output.root>/<WMO>/<plots.save.path>/{figure_name}.<plots.save.format>`

        This method may be in Calibration rather than CalibrationHTMLReport
        """

        # Save figures from the ArgoFloat instance:
        f = next(
            (f for f in do.figures if f.config_uid == f"{self.af.WMO}_trajectory_map"),
            None,
        )
        if f is None:
            f = (
                self.plot_float_traj()
            )  # Todo this is probably not the most appropriate place to create this figure if it's missing
        self._save_figure(f)

        # Save figures from the Calibration instance:
        for f in self.c.figures:
            self._save_figure(f)

        for icfg in range(self.c.n_configs):
            for f in self.c.configs_figures[icfg]:
                self._save_figure(f)

    def pydoxfig2templatefig(self, f: PydoxFigure) -> TemplateFigure:
        """Transform PydoxFigure instance into a dictionary usable within the Jinja2 template file"""
        return {
            "title": f.name,
            "category": f.category,
            "legend": f.legend if f.legend is not None else f.name,
            "uid": f.config_uid,
            "src": str(self.pm.relfpath(f.name)),  # Relative paths
            # 'src': str(self.pm.fpath(f.name)), # Absolute paths
        }

    def retrieve_appendix_figs(
        self, sort_by: str = "category"
    ) -> Dict[str, list[TemplateFigure]]:
        """Get all TemplateFigure instances to include in the appendix figure sections"""

        # Get all possible values for the sort_by key:
        sort_values = set([getattr(f, sort_by) for f in self.c.figures])
        sort_values_cfg = set(
            [
                getattr(f, sort_by)
                for icfg in range(self.c.n_configs)
                for f in self.c.configs_figures[icfg]
            ]
        )
        sort_values.update(sort_values_cfg)

        # Init the dict output:
        sorted_content = {}
        for val in sort_values:
            sorted_content[val]: list[TemplateFigure] = []

        # Fill in the list of TemplateFigure for each figure in each sort_by key:
        for f in self.c.figures:
            fobj = self.pydoxfig2templatefig(f)
            sorted_content[getattr(f, sort_by)].append(fobj)

        for icfg in range(self.c.n_configs):
            for f in self.c.configs_figures[icfg]:
                fobj = self.pydoxfig2templatefig(f)
                sorted_content[getattr(f, sort_by)].append(fobj)

        return sorted_content

    def publish(
        self, file_name: Optional[str] = None, include_static: bool = True, **kwargs
    ) -> Path:
        """Publish an HTML report file based on the template defined in settings

        Customizable fields can be provided with kwargs. These are:
        - 'summary'
        - 'introduction'
        - 'comment'

        They must contain strings, possibly with HTML code.

        Returns
        -------
        :class:`pathlib.Path`
            Path to published report, following the convention: `<output.root>/<WMO>/<reports.save.path>/<reports.save.prefix>{report_name}.<reports.save.format>`
        """

        #############
        # Produce and retrieve data for the report
        #############
        if include_static:
            self.save_static()
        self.save_figures()

        # Get TemplateFigure for: Float trajectory
        f_traj: PydoxFigure = next(
            f for f in do.figures if f.config_uid == f"{self.af.WMO}_trajectory_map"
        )  # save_figures() ensured this plot to exist
        f_traj: TemplateFigure = self.pydoxfig2templatefig(f_traj)

        # Get TemplateFigure(s) for: Best fit result (selected by user)
        f_plot_result: PydoxFigure | TemplateFigure | None = None
        target = (
            f"Calibration results [configs_layout='figure', iset='{self.c.best_fit}']"
        )
        for f in self.c.figures:
            # This name check must be consistant with name given to the figure by: do.calibration.methods.<method>.plots.plot_fit_results_figure()
            if f.name == target:
                f_plot_result = deepcopy(f)
                f_plot_result.legend = f"Calibration results obtained with configuration number {self.c.best_fit} (selected)"
                f_plot_result: TemplateFigure = self.pydoxfig2templatefig(f_plot_result)
                f_plot_result["title"] = f_plot_result["title"].split("[")[0]
                f_plot_result["title"] = f_plot_result["title"].strip()
        if f_plot_result is None:
            raise ValueError(f"Can't find the best fit result figure named: '{target}'")

        # Get all PydoxFigure objects to include in the appendix figure sections:
        sorted_content: Dict[str, list[TemplateFigure]] = self.retrieve_appendix_figs(
            sort_by="category"
        )

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
            # `reports.templates.pydox.html` setting has only the file name, not the path (to hide to users)
            # So we need to make the file path absolute for internal Pydox templates
            # Template files are located under the pydox install folder / static / templates / folder.
            html_template_file = _path2static.joinpath("templates").joinpath(
                html_template_file
            )

        loader = FileSystemLoader(
            str(html_template_file.parent)
        )  # from an absolute file path
        template = Environment(loader=loader).get_template(html_template_file.name)

        # Define template data
        # Because they depend on the template, this may need to be adapted to the template file
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

        if "discussion" not in template_kwargs:
            template_kwargs["discussion"] = html_default_discussion

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

        if "coefs" not in template_kwargs:
            template_kwargs["coefs"] = self.c.coefs

        if "configs" not in template_kwargs:
            template_kwargs["configs"] = self.c.configs

        template_kwargs["icon_orcid"] = self.pm.rroot_img.joinpath(
            "orcid_icon.png"
        ).relative_to(self.pm.rroot)

        template_kwargs["logo_pydox"] = self.pm.rroot_img.joinpath(
            "pydox-logo-long-800.png"
        ).relative_to(self.pm.rroot)

        #############
        # Finally render the template
        #############
        html = template.render(**template_kwargs)
        file_name: str = (
            "preliminary_report"
            if file_name is None
            else file_name.removesuffix(".html")
        )
        report_file = self.pm.rpath(file_name)
        if report_file.exists():
            log.warning(f"Saving HTML report to: {report_file} (⚠️ overwrite)")
        else:
            log.info(f"Saving HTML report to: {report_file}")

        with open(report_file, "w") as f:
            f.write(html)

        return report_file
