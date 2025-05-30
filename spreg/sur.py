"""
SUR and 3SLS estimation
"""

__author__ = "Luc Anselin lanselin@gmail.com,    \
             Pedro V. Amaral pedrovma@gmail.com"


import numpy as np
import numpy.linalg as la
from . import summary_output as SUMMARY
from . import user_output as USER
from . import regimes as REGI
from .sur_utils import (
    sur_dictxy,
    sur_dictZ,
    sur_corr,
    sur_crossprod,
    sur_est,
    sur_resids,
    sur_predict,
    check_k,
)
from .diagnostics_sur import (
    sur_setp,
    sur_lrtest,
    sur_lmtest,
    surLMe,
    surLMlag,
    sur_chow,
)
from .sputils import sphstack, spdot


__all__ = ["SUR", "ThreeSLS"]


class BaseSUR:
    """
    Base class for SUR estimation, both two step as well as iterated

    Parameters
    ----------

    bigy       : dictionary
                 with vector for dependent variable by equation
    bigX       : dictionary
                 with matrix of explanatory variables by equation
                 (note, already includes constant term)
    iter       : boolean
                 whether or not to use iterated estimation.
                 default = False
    maxiter    : int
                 maximum iterations; default = 5
    epsilon    : float
                 precision criterion to end iterations.
                 default = 0.00001
    verbose    : boolean
                 flag to print out iteration number and value of log det(sig)
                 at the beginning and the end of the iteration

    Attributes
    ----------
    bigy        : dictionary
                  with y values
    bigX        : dictionary
                  with X values
    bigXX       : dictionary
                  with :math:`X_t'X_r` cross-products
    bigXy       : dictionary
                  with :math:`X_t'y_r` cross-products
    n_eq        : int
                  number of equations
    n           : int
                  number of observations in each cross-section
    bigK        : array
                  vector with number of explanatory variables (including constant)
                  for each equation
    bOLS        : dictionary
                  with OLS regression coefficients for each equation
    olsE        : array
                  N x n_eq array with OLS residuals for each equation
    bSUR        : dictionary
                  with SUR regression coefficients for each equation
    varb        : array
                  variance-covariance matrix
    bigE        : array
                  N x n_eq array with SUR residuals for each equation
    bigYP       : array
                  N x n_eq array with SUR predicted values for each equation
    sig         : array
                  Sigma matrix of inter-equation error covariances
    ldetS1      : float
                  log det(Sigma) for SUR model
    resids      : array
                  n by n_eq array of residuals
    sig_ols     : array
                  Sigma matrix for OLS residuals
    ldetS0      : float
                  log det(Sigma) for null model (OLS by equation, diagonals only)
    niter       : int
                  number of iterations (=0 for iter=False)
    corr        : array
                  inter-equation SUR error correlation matrix
    llik        : float
                  log-likelihood (including the constant pi)
    """

    def __init__(
        self, bigy, bigX, iter=False, maxiter=5, epsilon=0.00001, verbose=False
    ):
        # setting up the cross-products
        self.bigy = bigy
        self.bigX = bigX
        self.n_eq = len(bigy.keys())
        self.n = bigy[0].shape[0]
        self.bigK = np.zeros((self.n_eq, 1), dtype=np.int_)
        for r in range(self.n_eq):
            self.bigK[r] = self.bigX[r].shape[1]
        self.bigXX, self.bigXy = sur_crossprod(self.bigX, self.bigy)
        # OLS regression by equation, sets up initial residuals
        _sur_ols(self)  # creates self.bOLS and self.olsE
        # SUR estimation using OLS residuals - two step estimation
        self.bSUR, self.varb, self.sig = sur_est(
            self.bigXX, self.bigXy, self.olsE, self.bigK
        )
        resids = sur_resids(self.bigy, self.bigX, self.bSUR)  # matrix of residuals
        # Sigma and log det(Sigma) for null model
        self.sig_ols = self.sig
        sols = np.diag(np.diag(self.sig))
        self.ldetS0 = np.log(np.diag(sols)).sum()
        det0 = self.ldetS0
        # setup for iteration
        det1 = la.slogdet(self.sig)[1]
        self.ldetS1 = det1
        # self.niter = 0
        if iter:  # iterated FGLS aka ML
            n_iter = 0
            while np.abs(det1 - det0) > epsilon and n_iter <= maxiter:
                n_iter += 1
                det0 = det1
                self.bSUR, self.varb, self.sig = sur_est(
                    self.bigXX, self.bigXy, resids, self.bigK
                )
                resids = sur_resids(self.bigy, self.bigX, self.bSUR)
                det1 = la.slogdet(self.sig)[1]
                if verbose:
                    print(n_iter, det0, det1)
            self.bigE = sur_resids(self.bigy, self.bigX, self.bSUR)
            self.ldetS1 = det1
            self.niter = n_iter
        else:
            self.niter = 1
            self.bigE = resids
        self.bigYP = sur_predict(self.bigy, self.bigX, self.bSUR)  # LA added 10/30/16
        self.corr = sur_corr(self.sig)
        lik = self.n_eq * (1.0 + np.log(2.0 * np.pi)) + self.ldetS1
        self.llik = -(self.n / 2.0) * lik


def _sur_ols(reg):
    """
    OLS estimation of SUR equations

    Parameters
    ----------
    reg  : BaseSUR object

    Return
    -------
    reg.bOLS    : dictionary
                 with regression coefficients for each equation
    reg.olsE    : array
                 N x n_eq array with OLS residuals for each equation

    """
    reg.bOLS = {}
    for r in range(reg.n_eq):
        reg.bOLS[r] = np.dot(la.inv(reg.bigXX[(r, r)]), reg.bigXy[(r, r)])
    reg.olsE = sur_resids(reg.bigy, reg.bigX, reg.bOLS)
    return reg


class SUR(BaseSUR, REGI.Regimes_Frame):
    """
    User class for SUR estimation, both two step as well as iterated

    Parameters
    ----------
    bigy       : list or dictionary
                 list with the name of the dependent variable for each equation
                 or dictionary with vectors for dependent variable by equation                  
    bigX       : list or dictionary
                 list of lists the name of the explanatory variables for each equation
                 or dictionary with matrix of explanatory variables by equation
                 (note, already includes constant term)  
    db         : Pandas DataFrame
                 Optional. Required in case bigy and bigX are lists with names of variables
    w          : spatial weights object
                 default = None
    regimes    : list
                 default = None.
                 List of n values with the mapping of each
                 observation to a regime. Assumed to be aligned with 'x'.
    nonspat_diag: boolean
                  flag for non-spatial diagnostics, default = True
    spat_diag  : boolean
                 flag for spatial diagnostics, default = False
    iter       : boolean
                 whether or not to use iterated estimation.
                 default = False
    maxiter    : int
                 maximum iterations; default = 5
    epsilon    : float
                 precision criterion to end iterations.
                 default = 0.00001
    verbose    : boolean
                 flag to print out iteration number and value
                 of log det(sig) at the beginning and the end of the iteration
    name_bigy  : dictionary
                 with name of dependent variable for each equation.
                 default = None, but should be specified
                 is done when sur_stackxy is used
    name_bigX  : dictionary
                 with names of explanatory variables for each equation.
                 default = None, but should be specified
                 is done when sur_stackxy is used
    name_ds    : string
                 name for the data set
    name_w     : string
                 name for the weights file
    name_regimes : string
                   name of regime variable for use in the output

    Attributes
    ----------
    bigy        : dictionary
                  with y values
    bigX        : dictionary
                  with X values
    bigXX       : dictionary
                  with :math:`X_t'X_r` cross-products
    bigXy       : dictionary
                  with :math:`X_t'y_r` cross-products
    n_eq        : int
                  number of equations
    n           : int
                  number of observations in each cross-section
    bigK        : array
                  vector with number of explanatory variables (including constant)
                  for each equation
    bOLS        : dictionary
                  with OLS regression coefficients for each equation
    olsE        : array
                  N x n_eq array with OLS residuals for each equation
    bSUR        : dictionary
                  with SUR regression coefficients for each equation
    varb        : array
                  variance-covariance matrix
    bigE        : array
                  n by n_eq array of residuals
    sig_ols     : array
                  Sigma matrix for OLS residuals (diagonal)
    ldetS0      : float
                  log det(Sigma) for null model (OLS by equation)
    niter       : int
                  number of iterations (=0 for iter=False)
    corr        : array
                  inter-equation error correlation matrix
    llik        : float
                  log-likelihood (including the constant pi)
    sur_inf     : dictionary
                  with standard error, asymptotic t and p-value,
                  one for each equation
    lrtest      : tuple
                  Likelihood Ratio test on off-diagonal elements of sigma
                  (tuple with test,df,p-value)
    lmtest      : tuple
                  Lagrange Multipler test on off-diagonal elements of sigma
                  (tuple with test,df,p-value)
    lmEtest     : tuple
                  Lagrange Multiplier test on error spatial autocorrelation in SUR
                  (tuple with test, df, p-value)
    lmlagtest   : tuple
                  Lagrange Multiplier test on spatial lag autocorrelation in SUR
                  (tuple with test, df, p-value)
    surchow     : array
                  list with tuples for Chow test on regression coefficients.
                  each tuple contains test value, degrees of freedom, p-value
    name_bigy   : dictionary
                  with name of dependent variable for each equation
    name_bigX   : dictionary
                  with names of explanatory variables for each
                  equation
    name_ds     : string
                  name for the data set
    name_w      : string
                  name for the weights file
    name_regimes : string
                   name of regime variable for use in the output


    Examples
    --------

    >>> import libpysal
    >>> import geopandas as gpd
    >>> from spreg import SUR

    Open data on NCOVR US County Homicides (3085 areas) from libpysal examples using geopandas.

    >>> nat = libpysal.examples.load_example('Natregimes')
    >>> df = gpd.read_file(nat.get_path("natregimes.shp"))

    The specification of the model to be estimated can be provided as lists.
    Each equation should be listed separately. In this example, equation 1
    has HR80 as dependent variable and PS80 and UE80 as exogenous regressors.
    For equation 2, HR90 is the dependent variable, and PS90 and UE90 the
    exogenous regressors.

    >>> y_var = ['HR80','HR90']
    >>> x_var = [['PS80','UE80'],['PS90','UE90']]

    Although not required for this method, we can create a weights matrix 
    to allow for spatial diagnostics.

    >>> w = libpysal.weights.Queen.from_dataframe(df)
    >>> w.transform='r'

    We can now run the regression and then have a summary of the output by typing:
    'print(reg.summary)'

    >>> reg = SUR(y_var,x_var,df=df,w=w,spat_diag=True,name_ds="nat")
    >>> print(reg.summary)
    REGRESSION
    ----------
    SUMMARY OF OUTPUT: SEEMINGLY UNRELATED REGRESSIONS (SUR)
    --------------------------------------------------------
    Data set            :         nat
    Weights matrix      :     unknown
    Number of Equations :           2                Number of Observations:        3085
    Log likelihood (SUR):  -19902.966                Number of Iterations  :           1
    ----------
    <BLANKLINE>
    SUMMARY OF EQUATION 1
    ---------------------
    Dependent Variable  :        HR80                Number of Variables   :           3
    Mean dependent var  :      6.9276                Degrees of Freedom    :        3082
    S.D. dependent var  :      6.8251
    <BLANKLINE>
    ------------------------------------------------------------------------------------
                Variable     Coefficient       Std.Error     z-Statistic     Probability
    ------------------------------------------------------------------------------------
              Constant_1       5.1390718       0.2624673      19.5798587       0.0000000
                    PS80       0.6776481       0.1219578       5.5564132       0.0000000
                    UE80       0.2637240       0.0343184       7.6846277       0.0000000
    ------------------------------------------------------------------------------------
    <BLANKLINE>
    SUMMARY OF EQUATION 2
    ---------------------
    Dependent Variable  :        HR90                Number of Variables   :           3
    Mean dependent var  :      6.1829                Degrees of Freedom    :        3082
    S.D. dependent var  :      6.6403
    <BLANKLINE>
    ------------------------------------------------------------------------------------
                Variable     Coefficient       Std.Error     z-Statistic     Probability
    ------------------------------------------------------------------------------------
              Constant_2       3.6139403       0.2534996      14.2561949       0.0000000
                    PS90       1.0260715       0.1121662       9.1477755       0.0000000
                    UE90       0.3865499       0.0341996      11.3027760       0.0000000
    ------------------------------------------------------------------------------------
    <BLANKLINE>
    <BLANKLINE>
    REGRESSION DIAGNOSTICS
                                         TEST         DF       VALUE           PROB
                             LM test on Sigma         1      680.168           0.0000
                             LR test on Sigma         1      768.385           0.0000
    <BLANKLINE>
    OTHER DIAGNOSTICS - CHOW TEST BETWEEN EQUATIONS
                                    VARIABLES         DF       VALUE           PROB
                       Constant_1, Constant_2         1       26.729           0.0000
                                   PS80, PS90         1        8.241           0.0041
                                   UE80, UE90         1        9.384           0.0022
    <BLANKLINE>
    DIAGNOSTICS FOR SPATIAL DEPENDENCE
    TEST                              DF       VALUE           PROB
    Lagrange Multiplier (error)       2        1333.586        0.0000
    Lagrange Multiplier (lag)         2        1275.821        0.0000
    <BLANKLINE>
    ERROR CORRELATION MATRIX
      EQUATION 1  EQUATION 2
        1.000000    0.469548
        0.469548    1.000000
    ================================ END OF REPORT =====================================
    """

    def __init__(
        self,
        bigy,
        bigX,
        df=None,
        w=None,
        regimes=None,
        nonspat_diag=True,
        spat_diag=False,
        vm=False,
        iter=False,
        maxiter=5,
        epsilon=0.00001,
        verbose=False,
        name_bigy=None,
        name_bigX=None,
        name_ds=None,
        name_w=None,
        name_regimes=None,
    ):

        if isinstance(bigy, list) or isinstance(bigX, list):
            if isinstance(bigy, list) and isinstance(bigX, list):            
                if len(bigy) == len(bigX):
                    if df is not None:
                        bigy,bigX,name_bigy,name_bigX = sur_dictxy(df,bigy,bigX)
                    else:
                        raise Exception("Error: df argument is required if bigy and bigX are lists")
                else:
                    raise Exception("Error: bigy and bigX must have the same number of elements")
            else:
                raise Exception("Error: bigy and bigX must be both lists or both dictionaries")

        self.name_ds = USER.set_name_ds(name_ds)
        self.name_w = USER.set_name_w(name_w, w)
        self.n_eq = len(bigy.keys())

        # initialize names - should be generated by sur_stack
        if name_bigy:
            self.name_bigy = name_bigy
        else:  # need to construct y names
            self.name_bigy = {}
            for r in range(self.n_eq):
                yn = "dep_var_" + str(r)
                self.name_bigy[r] = yn
        if name_bigX is None:
            name_bigX = {}
            for r in range(self.n_eq):
                #k = self.bigX[r].shape[1] - 1
                k = bigX[r].shape[1] - 1
                name_x = ["var_" + str(i + 1) + "_" + str(r) for i in range(k)]
                ct = "Constant_" + str(r)  # NOTE: constant always included in X
                name_x.insert(0, ct)
                name_bigX[r] = name_x

        if regimes is not None:
            self.constant_regi = "many"
            self.cols2regi = "all"
            self.regime_err_sep = False
            self.name_regimes = USER.set_name_ds(name_regimes)
            self.regimes_set = REGI._get_regimes_set(regimes)
            self.regimes = regimes
            self.name_x_r = name_bigX
            cols2regi_dic = {}
            self.name_bigX = {}
            for r in range(self.n_eq):
                cols2regi_dic[r] = REGI.check_cols2regi(
                    self.constant_regi, self.cols2regi, bigX[r], add_cons=False
                )
                USER.check_regimes(self.regimes_set, bigy[0].shape[0], bigX[r].shape[1])
                bigX[r], self.name_bigX[r], xtype = REGI.Regimes_Frame.__init__(
                    self,
                    bigX[r],
                    regimes,
                    constant_regi=None,
                    cols2regi=cols2regi_dic[r],
                    names=name_bigX[r],
                )
        else:
            self.name_bigX = name_bigX

        # need checks on match between bigy, bigX dimensions
        # init moved here before name check
        BaseSUR.__init__(
            self,
            bigy=bigy,
            bigX=bigX,
            iter=iter,
            maxiter=maxiter,
            epsilon=epsilon,
            verbose=verbose,
        )

        # inference
        self.sur_inf = sur_setp(self.bSUR, self.varb)

        if nonspat_diag:
            # LR test on off-diagonal elements of Sigma
            self.lrtest = sur_lrtest(self.n, self.n_eq, self.ldetS0, self.ldetS1)

            # LM test on off-diagonal elements of Sigma
            self.lmtest = sur_lmtest(self.n, self.n_eq, self.sig_ols)
        else:
            self.lrtest = None
            self.lmtest = None

        if spat_diag:
            if not w:
                raise Exception("Error: spatial weights needed")
            WS = w.sparse
            # LM test on spatial error autocorrelation
            self.lmEtest = surLMe(self.n_eq, WS, self.bigE, self.sig)
            # LM test on spatial lag autocorrelation
            self.lmlagtest = surLMlag(
                self.n_eq,
                WS,
                self.bigy,
                self.bigX,
                self.bigE,
                self.bigYP,
                self.sig,
                self.varb,
            )
        else:
            self.lmEtest = None
            self.lmlagtest = None

        # test on constancy of coefficients across equations
        if check_k(self.bigK):  # only for equal number of variables
            self.surchow = sur_chow(self.n_eq, self.bigK, self.bSUR, self.varb)
        else:
            self.surchow = None

        # Listing of the results
        self.title = "SEEMINGLY UNRELATED REGRESSIONS (SUR)"
        if regimes is not None:
            self.title += " - REGIMES"
            self.chow_regimes = {}
            varb_counter = 0
            for r in range(self.n_eq):
                counter_end = varb_counter + self.bSUR[r].shape[0]
                self.chow_regimes[r] = REGI._chow_run(
                    len(cols2regi_dic[r]),
                    0,
                    0,
                    len(self.regimes_set),
                    self.bSUR[r],
                    self.varb[varb_counter:counter_end, varb_counter:counter_end],
                )
                varb_counter = counter_end
            regimes = True

        SUMMARY.SUR(
            reg=self,
            nonspat_diag=nonspat_diag,
            spat_diag=spat_diag,
            surlm=True,
            regimes=regimes,
        )


class BaseThreeSLS:
    """
    Base class for 3SLS estimation, two step

    Parameters
    ----------
    bigy       : dictionary
                 with vector for dependent variable by equation
    bigX       : dictionary
                 with matrix of explanatory variables by equation
                 (note, already includes constant term)
    bigyend    : dictionary
                 with matrix of endogenous variables by equation
    bigq       : dictionary
                 with matrix of instruments by equation    

    Attributes
    ----------
    bigy        : dictionary
                  with y values
    bigZ        : dictionary
                  with matrix of exogenous and endogenous variables
                  for each equation
    bigZHZH     : dictionary
                  with matrix of cross products Zhat_r'Zhat_s
    bigZHy      : dictionary
                  with matrix of cross products Zhat_r'y_end_s
    n_eq        : int
                  number of equations
    n           : int
                  number of observations in each cross-section
    bigK        : array
                  vector with number of explanatory variables (including constant,
                  exogenous and endogenous) for each equation
    b2SLS       : dictionary
                  with 2SLS regression coefficients for each equation
    tslsE       : array
                  N x n_eq array with OLS residuals for each equation
    b3SLS       : dictionary
                  with 3SLS regression coefficients for each equation
    varb        : array
                  variance-covariance matrix
    sig         : array
                  Sigma matrix of inter-equation error covariances
    bigE        : array
                  n by n_eq array of residuals
    corr        : array
                  inter-equation 3SLS error correlation matrix

    """

    def __init__(self, bigy, bigX, bigyend, bigq):
        # setting up the cross-products
        self.bigy = bigy
        self.n_eq = len(bigy.keys())
        self.n = bigy[0].shape[0]
        # dictionary with exog and endog, Z
        self.bigZ = {}
        for r in range(self.n_eq):
            self.bigZ[r] = sphstack(bigX[r], bigyend[r])
        # number of explanatory variables by equation
        self.bigK = np.zeros((self.n_eq, 1), dtype=np.int_)
        for r in range(self.n_eq):
            self.bigK[r] = self.bigZ[r].shape[1]
        # dictionary with instruments, H
        bigH = {}
        for r in range(self.n_eq):
            bigH[r] = sphstack(bigX[r], bigq[r])
        # dictionary with instrumental variables, X and yend_predicted, Z-hat
        bigZhat = _get_bigZhat(self, bigX, bigyend, bigH)
        self.bigZHZH, self.bigZHy = sur_crossprod(bigZhat, self.bigy)

        # 2SLS regression by equation, sets up initial residuals
        _sur_2sls(self)  # creates self.b2SLS and self.tslsE

        self.b3SLS, self.varb, self.sig = sur_est(
            self.bigZHZH, self.bigZHy, self.tslsE, self.bigK
        )
        self.bigE = sur_resids(self.bigy, self.bigZ, self.b3SLS)  # matrix of residuals

        # inter-equation correlation matrix
        self.corr = sur_corr(self.sig)


class ThreeSLS(BaseThreeSLS, REGI.Regimes_Frame):
    """
    User class for 3SLS estimation

    Parameters
    ----------
    bigy       : list or dictionary
                 list with the names of the dependent variable for each equation
                 or dictionary with vectors for dependent variable by equation                  
    bigX       : list or dictionary
                 list of lists the names of the explanatory variables for each equation
                 or dictionary with matrix of explanatory variables by equation
                 (note, already includes constant term)                 
    bigyend    : list or dictionary
                 list of lists the names of the endogenous variables for each equation
                 or dictionary with matrix of endogenous variables by equation
    bigq       : list or dictionary
                 list of lists the names of the instrument variables for each equation
                 or dictionary with matrix of instruments by equation
    db         : Pandas DataFrame
                 Optional. Required in case bigy and bigX are lists with names of variables
    regimes    : list
                 List of n values with the mapping of each
                 observation to a regime. Assumed to be aligned with 'x'.
    nonspat_diag: boolean
                  flag for non-spatial diagnostics, default = True.
    name_bigy  : dictionary
                 with name of dependent variable for each equation.
                 default = None, but should be specified.
                 is done when sur_stackxy is used
    name_bigX  : dictionary
                 with names of explanatory variables for each equation.
                 default = None, but should be specified.
                 is done when sur_stackxy is used
    name_bigyend : dictionary
                   with names of endogenous variables for each equation.
                   default = None, but should be specified.
                   is done when sur_stackZ is used
    name_bigq  : dictionary
                 with names of instrumental variables for each equation.
                 default = None, but should be specified.
                 is done when sur_stackZ is used.
    name_ds    : string
                 name for the data set.
    name_regimes : string
                   name of regime variable for use in the output.

    Attributes
    ----------

    bigy        : dictionary
                  with y values
    bigZ        : dictionary
                  with matrix of exogenous and endogenous variables
                  for each equation
    bigZHZH     : dictionary
                  with matrix of cross products Zhat_r'Zhat_s
    bigZHy      : dictionary
                  with matrix of cross products Zhat_r'y_end_s
    n_eq        : int
                  number of equations
    n           : int
                  number of observations in each cross-section
    bigK        : array
                  vector with number of explanatory variables (including constant,
                  exogenous and endogenous) for each equation
    b2SLS       : dictionary
                  with 2SLS regression coefficients for each equation
    tslsE       : array
                  N x n_eq array with OLS residuals for each equation
    b3SLS       : dictionary
                  with 3SLS regression coefficients for each equation
    varb        : array
                  variance-covariance matrix
    sig         : array
                  Sigma matrix of inter-equation error covariances
    bigE        : array
                  n by n_eq array of residuals
    corr        : array
                  inter-equation 3SLS error correlation matrix
    tsls_inf    : dictionary
                  with standard error, asymptotic t and p-value,
                  one for each equation
    surchow     : array
                  list with tuples for Chow test on regression coefficients
                  each tuple contains test value, degrees of freedom, p-value
    name_ds    : string
                 name for the data set
    name_bigy  : dictionary
                 with name of dependent variable for each equation
    name_bigX  : dictionary
                 with names of explanatory variables for each
                 equation
    name_bigyend : dictionary
                   with names of endogenous variables for each
                   equation
    name_bigq  : dictionary
                 with names of instrumental variables for each
                 equations
    name_regimes : string
                   name of regime variable for use in the output


    Examples
    --------
    
    >>> import libpysal
    >>> import geopandas as gpd
    >>> from spreg import ThreeSLS
    >>> import numpy as np
    >>> np.set_printoptions(suppress=True) #prevent scientific format

    Open data on NCOVR US County Homicides (3085 areas) from libpysal examples using geopandas.

    >>> nat = libpysal.examples.load_example('Natregimes')
    >>> df = gpd.read_file(nat.get_path("natregimes.shp"))

    The specification of the model to be estimated can be provided as lists.
    Each equation should be listed separately. In this example, equation 1
    has HR80 as dependent variable, PS80 and UE80 as exogenous regressors,
    RD80 as endogenous regressor and FP79 as additional instrument.
    For equation 2, HR90 is the dependent variable, PS90 and UE90 the
    exogenous regressors, RD90 as endogenous regressor and FP99 as
    additional instrument

    >>> y_var = ['HR80','HR90']
    >>> x_var = [['PS80','UE80'],['PS90','UE90']]
    >>> yend_var = [['RD80'],['RD90']]
    >>> q_var = [['FP79'],['FP89']]

    We can now run the regression and then have a summary of the output by typing:
    print(reg.summary)

    Alternatively, we can just check the betas and standard errors, asymptotic t
    and p-value of the parameters:

    >>> reg = ThreeSLS(y_var,x_var,yend_var,q_var,df=df,name_ds="NAT")
    >>> reg.b3SLS
    {0: array([[6.92426353],
           [1.42921826],
           [0.00049435],
           [3.5829275 ]]), 1: array([[ 7.62385875],
           [ 1.65031181],
           [-0.21682974],
           [ 3.91250428]])}

    >>> reg.tsls_inf
    {0: array([[ 0.23220853, 29.81916157,  0.        ],
           [ 0.10373417, 13.77770036,  0.        ],
           [ 0.03086193,  0.01601807,  0.98721998],
           [ 0.11131999, 32.18584124,  0.        ]]), 1: array([[ 0.28739415, 26.52753638,  0.        ],
           [ 0.09597031, 17.19606554,  0.        ],
           [ 0.04089547, -5.30204786,  0.00000011],
           [ 0.13586789, 28.79638723,  0.        ]])}

    """

    def __init__(
        self,
        bigy,
        bigX,
        bigyend,
        bigq,
        df=None,
        regimes=None,
        nonspat_diag=True,
        name_bigy=None,
        name_bigX=None,
        name_bigyend=None,
        name_bigq=None,
        name_ds=None,
        name_regimes=None,
    ):

        if isinstance(bigy, list) or isinstance(bigX, list) or isinstance(bigyend, list) or isinstance(bigq, list):
            if isinstance(bigy, list) and isinstance(bigX, list) and isinstance(bigyend, list) and isinstance(bigq, list):        
                if len(bigy) == len(bigX) == len(bigyend) == len(bigq):
                    if df is not None:
                        bigy,bigX,name_bigy,name_bigX = sur_dictxy(df,bigy,bigX)
                        bigyend,name_bigyend = sur_dictZ(df,bigyend)
                        bigq,name_bigq = sur_dictZ(df,bigq)                        
                    else:
                        raise Exception("Error: df argument is required if bigy, bigX, bigyend and bigq are lists")
                else:
                    raise Exception("Error: bigy, bigX, bigyend and bigq must have the same number of elements")
            else:
                raise Exception("Error: bigy, bigX, bigyend and bigq must be all lists or all dictionaries")

        self.name_ds = USER.set_name_ds(name_ds)
        self.n_eq = len(bigy.keys())

        # initialize names - should be generated by sur_stack
        if name_bigy:
            self.name_bigy = name_bigy
        else:  # need to construct y names
            self.name_bigy = {}
            for r in range(self.n_eq):
                yn = "dep_var_" + str(r + 1)
                self.name_bigy[r] = yn

        if name_bigX is None:
            name_bigX = {}
            for r in range(self.n_eq):
                k = bigX[r].shape[1] - 1
                name_x = ["var_" + str(i + 1) + "_" + str(r + 1) for i in range(k)]
                ct = "Constant_" + str(r + 1)  # NOTE: constant always included in X
                name_x.insert(0, ct)
                name_bigX[r] = name_x

        if name_bigyend is None:
            name_bigyend = {}
            for r in range(self.n_eq):
                ky = bigyend[r].shape[1]
                name_ye = ["end_" + str(i + 1) + "_" + str(r + 1) for i in range(ky)]
                name_bigyend[r] = name_ye

        if name_bigq is None:
            name_bigq = {}
            for r in range(self.n_eq):
                ki = bigq[r].shape[1]
                name_i = ["inst_" + str(i + 1) + "_" + str(r + 1) for i in range(ki)]
                name_bigq[r] = name_i

        if regimes is not None:
            self.constant_regi = "many"
            self.cols2regi = "all"
            self.regime_err_sep = False
            self.name_regimes = USER.set_name_ds(name_regimes)
            self.regimes_set = REGI._get_regimes_set(regimes)
            self.regimes = regimes
            cols2regi_dic = {}
            self.name_bigX, self.name_x_r, self.name_bigq, self.name_bigyend = (
                {},
                {},
                {},
                {},
            )

            for r in range(self.n_eq):
                self.name_x_r[r] = name_bigX[r] + name_bigyend[r]
                cols2regi_dic[r] = REGI.check_cols2regi(
                    self.constant_regi,
                    self.cols2regi,
                    bigX[r],
                    yend=bigyend[r],
                    add_cons=False,
                )
                USER.check_regimes(self.regimes_set, bigy[0].shape[0], bigX[r].shape[1])
                bigX[r], self.name_bigX[r], xtype = REGI.Regimes_Frame.__init__(
                    self,
                    bigX[r],
                    regimes,
                    constant_regi=None,
                    cols2regi=cols2regi_dic[r],
                    names=name_bigX[r],
                )
                bigq[r], self.name_bigq[r], xtype = REGI.Regimes_Frame.__init__(
                    self,
                    bigq[r],
                    regimes,
                    constant_regi=None,
                    cols2regi="all",
                    names=name_bigq[r],
                )
                bigyend[r], self.name_bigyend[r], xtype = REGI.Regimes_Frame.__init__(
                    self,
                    bigyend[r],
                    regimes,
                    constant_regi=None,
                    cols2regi=cols2regi_dic[r],
                    yend=True,
                    names=name_bigyend[r],
                )
        else:
            self.name_bigX, self.name_bigq, self.name_bigyend = (
                name_bigX,
                name_bigq,
                name_bigyend,
            )
        # need checks on match between bigy, bigX dimensions
        BaseThreeSLS.__init__(self, bigy=bigy, bigX=bigX, bigyend=bigyend, bigq=bigq)

        # inference
        self.tsls_inf = sur_setp(self.b3SLS, self.varb)

        # test on constancy of coefficients across equations
        if check_k(self.bigK):  # only for equal number of variables
            self.surchow = sur_chow(self.n_eq, self.bigK, self.b3SLS, self.varb)
        else:
            self.surchow = None

        # Listing of the results
        self.title = "THREE STAGE LEAST SQUARES (3SLS)"
        if regimes is not None:
            self.title += " - REGIMES"
            self.chow_regimes = {}
            varb_counter = 0
            for r in range(self.n_eq):
                counter_end = varb_counter + self.b3SLS[r].shape[0]
                self.chow_regimes[r] = REGI._chow_run(
                    len(cols2regi_dic[r]),
                    0,
                    0,
                    len(self.regimes_set),
                    self.b3SLS[r],
                    self.varb[varb_counter:counter_end, varb_counter:counter_end],
                )
                varb_counter = counter_end
            regimes = True

        SUMMARY.SUR(
            reg=self, tsls=True, ml=False, nonspat_diag=nonspat_diag, regimes=regimes
        )


def _sur_2sls(reg):
    """
     2SLS estimation of SUR equations

    Parameters
    ----------

    reg  : BaseSUR object

    Return
    ------

    reg.b2SLS    : dictionary
                   with regression coefficients for each equation
    reg.tslsE    : array
                   N x n_eq array with OLS residuals for each equation

    """
    reg.b2SLS = {}
    for r in range(reg.n_eq):
        reg.b2SLS[r] = np.dot(la.inv(reg.bigZHZH[(r, r)]), reg.bigZHy[(r, r)])
    reg.tslsE = sur_resids(reg.bigy, reg.bigZ, reg.b2SLS)
    return reg


def _get_bigZhat(reg, bigX, bigyend, bigH):
    bigZhat = {}
    for r in range(reg.n_eq):
        try:
            HHi = la.inv(spdot(bigH[r].T, bigH[r]))
        except:
            raise Exception("ERROR: singular cross product matrix, check instruments")
        Hye = spdot(bigH[r].T, bigyend[r])
        yp = spdot(bigH[r], spdot(HHi, Hye))
        bigZhat[r] = sphstack(bigX[r], yp)
    return bigZhat


def _test():
    import doctest

    start_suppress = np.get_printoptions()["suppress"]
    np.set_printoptions(suppress=True)
    doctest.testmod()
    np.set_printoptions(suppress=start_suppress)


if __name__ == "__main__":
    _test()
    import numpy as np
    import libpysal
    from .sur_utils import sur_dictxy
    from libpysal.examples import load_example

    nat = load_example("Natregimes")
    db = libpysal.io.open(nat.get_path("NAT.dbf"), "r")
    y_var = ["HR80", "HR90"]
    x_var = [["PS80", "UE80"], ["PS90", "UE90"]]

    # Example SUR
    # """
    w = libpysal.weights.Queen.from_shapefile(nat.get_path("natregimes.shp"))
    w.transform = "r"
    bigy0, bigX0, bigyvars0, bigXvars0 = sur_dictxy(db, y_var, x_var)
    reg0 = SUR(
        bigy0,
        bigX0,
        w=w,
        regimes=None,
        name_bigy=bigyvars0,
        name_bigX=bigXvars0,
        spat_diag=True,
        name_ds="NAT",
    )
    print(reg0.summary)
    """
    #Example 3SLS
    yend_var = [['RD80'],['RD90']]
    q_var = [['FP79'],['FP89']]

    bigy1,bigX1,bigyvars1,bigXvars1 = sur_dictxy(db,y_var,x_var)
    bigyend1,bigyendvars1 = sur_dictZ(db,yend_var)
    bigq1,bigqvars1 = sur_dictZ(db,q_var)

    reg1 = ThreeSLS(bigy1,bigX1,bigyend1,bigq1,regimes=regimes,name_bigy=bigyvars1,name_bigX=bigXvars1,name_bigyend=bigyendvars1,name_bigq=bigqvars1,name_ds="NAT",name_regimes="South")

    print reg1.summary
    #"""
