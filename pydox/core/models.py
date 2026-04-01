def AXplusB(X, A, B):
    """Function to estimate, with curve_fit, a line Y = AX + B

    Parameters
    ----------
    X : Values

    Returns
    --------
    A*X + B
    """
    return A * X + B


def Gain(X, G):
    """Function to estimate, with curve_fit, a correction with a Gain

    Parameters
    ----------
    X : Oxygen Values

    Returns
    --------
    G * X
    """
    return G * X


def Gain_Derive(X, G, D):
    """Function to estimate, with curve_fit, a correction with a Time Drift and a Gain

    Parameters
    ----------
    X : Oxygen Values (X[0]) and delta_T from launch_date (X[1])

    Returns
    --------
    G * (1 + (D * X[1])/(365*100)) * X[0]
    """
    return G * (1 + (D * X[1]) / (365 * 100)) * X[0]


def Gain_CarryOver(X, G, C):
    """Function to estimate, with curve_fit, a correction with a Gain using CarryOver (for NCEP correction only)

    Parameters
    -----------
    X contains PPOX in air (X[0]) and PPOX in Water (X[1])

    Returns
    --------
    G * (X[0] - abs(C) * X[1]) / (1 - abs(C))
    """
    return G * (X[0] - abs(C) * X[1]) / (1 - abs(C))  # C : Carry-over


def Gain_Derive_CarryOver(X, G, C, D):
    """Function to estimate, with curve_fit, a correction with a Time Drift and a Gain using CarryOver (for NCEP correction only)

    Parameters
    ----------
    X contains PPOX in air (X[0]), PPOX in water (X[1]) and delta_T from launch_date (X[2])

    Returns
    G / (1-abs(C)) * (1 + D / 100 * X[2]/365) * (X[0] - abs(C) * X[1])
    """
    return G / (1 - abs(C)) * (1 + D / 100 * X[2] / 365) * (X[0] - abs(C) * X[1])


def Gain_pres(X, G, Gp, coef2, coef3):
    """Function to estimate a CTD and a pressure effect correction (with curve_fit)

    Parameters
    ----------
    X: contains Oxygen (X[0]), Pressure (X[1]) and Temperature Values (X[2])
    coef2, coef3 : sensor depedant (aanderaa or rinko)
    Returns
    -------
    (G*(1 + Gp * X[1]/1000) * X[0]))
    """
    return (
        G
        * (
            1 / (1 + (coef2 * X[2] + coef3) * X[1] / 1000)
        )  # undo the correction pressure effect already done by coriolis
        * (1 + (coef2 * X[2] + Gp) * X[1] / 1000)
        * X[0]
    )


def Gain_pres_old(X, G, Gp):
    """Function to estimate a CTD and a pressure effect correction (with curve_fit)

    Parameters
    ----------
    X: contains Oxygen and Pressure  Values (X[0] and Pressure X[1])

    Returns
    -------
    (G*(1 + Gp * X[1]/1000) * X[0]))
    """
    return G * (1 + Gp * X[1] / 1000) * X[0]


def corr_pres(X, Gp):
    """Function to estimate a CTD pressure effect correction (with curve_fit)

    Parameters
    ----------
    X: contains Oxygen Values (X[0] and Pressure X[1])

    Returns
    -------
    (1 + Gp * X[1]/1000) * X[0])
    """
    return (1 + Gp * X[1] / 1000) * X[0]
