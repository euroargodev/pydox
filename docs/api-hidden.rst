.. Generate API reference pages, but don't display these in tables.
.. This extra page is a work around for sphinx not having any support for
.. hiding an autosummary table.

.. autosummary::
    :toctree: generated/

    pydox

    pydox.params
    pydox.set_params
    pydox.get_params
    pydox.reset_params
    pydox.config_print
    pydox.config_files
    pydox.get_configdir

    pydox.calibration.spec.Workflow
    pydox.calibration.spec.Workflow.uid

    pydox.Calibration

    pydox.calibration.MethodInAir
    pydox.calibration.MethodInAir.set_params
    pydox.calibration.MethodInAir.n_configs
    pydox.calibration.MethodInAir.fit
    pydox.calibration.MethodInAir.plot
    pydox.calibration.MethodInAir.set_best_fit
    pydox.calibration.MethodInAir.best_fit
    pydox.calibration.MethodInAir.create_corrBfile
    pydox.calibration.MethodInAir.to_report

    pydox.calibration.MethodInAir.uid
    pydox.calibration.MethodInAir.get_params
    pydox.calibration.MethodInAir.reset_params
    pydox.calibration.MethodInAir.flatten_configs
    pydox.calibration.MethodInAir.load_input_data

    pydox.calibration.MethodClimatology
    pydox.calibration.MethodClimatology.fit

    pydox.CalibrationSet
    pydox.CalibrationSet.set_params
    pydox.CalibrationSet.n_configs
    pydox.CalibrationSet.commit
    pydox.CalibrationSet.fit
    pydox.CalibrationSet.plot
    pydox.CalibrationSet.set_best_fit
    pydox.CalibrationSet.best_fit
    pydox.CalibrationSet.create_corrBfile
    pydox.CalibrationSet.to_report

    pydox.commodities.Data
    pydox.commodities.Data.value
    pydox.commodities.Data.error

    pydox.commodities.ParameterSet
    pydox.commodities.ParameterSet.uid
    pydox.commodities.ParameterSet.fit_drift
    pydox.commodities.ParameterSet.initial_gain
    pydox.commodities.ParameterSet.initial_drift
    pydox.commodities.ParameterSet.cycles

    pydox.commodities.Params
    pydox.commodities.Params
    pydox.commodities.Params.uid
    pydox.commodities.Params.fit_drift
    pydox.commodities.Params.initial_gain
    pydox.commodities.Params.initial_drift
    pydox.commodities.Params.cycles

    pydox.commodities.ParamsInAir
    pydox.commodities.ParamsClimatology

    pydox.commodities.VALID_FIGURE_CATEGORIES
    pydox.commodities.TPlotParams
    pydox.commodities.PlotParams
    pydox.commodities.PlotParams.get
    pydox.commodities.PlotParams.level
    pydox.commodities.PlotParams.watermark
    pydox.commodities.PlotParams.dpi
    pydox.commodities.PlotParams.uid

    pydox.commodities.PydoxFigure
    pydox.commodities.PydoxFigure.level
    pydox.commodities.PydoxFigure.uid
    pydox.commodities.PydoxFigure.reload
    pydox.commodities.PydoxFigure.show
    pydox.commodities.PydoxFigure.fig
    pydox.commodities.PydoxFigure.name
    pydox.commodities.PydoxFigure.legend
    pydox.commodities.PydoxFigure.category
    pydox.commodities.PydoxFigure.config_uid
    pydox.commodities.PydoxFigure.pickle
    pydox.commodities.PydoxFigure.caller

    pydox.reporting.CalibrationHTMLReport
    pydox.reporting.CalibrationHTMLReport.save_figures
    pydox.reporting.CalibrationHTMLReport.publish
    pydox.reporting.CalibrationHTMLReport.pydoxfig2templatefig
    pydox.reporting.CalibrationHTMLReport.retrieve_appendix_figs
    pydox.reporting.CalibrationHTMLReport.save_static
    pydox.reporting.CalibrationHTMLReport.plot_float_traj
    pydox.reporting.html.TemplateFigure

    pydox.figures
    pydox.figures.commit
    pydox.figures.to_pdf
    pydox.figures.orpheans
    pydox.figures.clear
    pydox.figures.uidstartswith

    pydox.tmp_root