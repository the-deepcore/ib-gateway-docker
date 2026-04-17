from typing import Callable, Dict, Optional

import numpy as np
import pandas as pd

# ---------- Core transforms (stateless) ----------



def identity(s: pd.Series) -> pd.Series:
    """Return the series unchanged."""
    return pd.to_numeric(s, errors="coerce")

def inv(s: pd.Series) -> pd.Series:
    """Log-returns: log(s).diff(periods). Nan si s <= 0."""
    x = pd.to_numeric(s, errors="coerce")
    inv= (1/x).replace([-np.inf, np.inf], np.nan).dropna()
    return inv
def mult(s: pd.Series, coeff: float) -> pd.Series:
    """Return the series unchanged."""
    return pd.to_numeric(coeff*s, errors="coerce")

def add(s: pd.Series, amount: float) -> pd.Series:
    """Return the series unchanged."""
    return pd.to_numeric(s + amount, errors="coerce")

def returns(s: pd.Series) -> pd.Series:
    """Return the pct_change series."""
    return pd.to_numeric(s, errors="coerce").pct_change().replace([np.inf, -np.inf], np.nan).fillna(0)

def logret(s: pd.Series, periods: int = 1) -> pd.Series:
    """Log-returns: log(s).diff(periods). Nan si s <= 0."""
    x = pd.to_numeric(s, errors="coerce")
    x = x.where(x > 0) 
    return np.log(x).diff(int(periods))

def sma(s: pd.Series, window: int) -> pd.Series:
    """Simple moving average."""
    return pd.to_numeric(s, errors="coerce").rolling(window=window, min_periods=window).mean()

def ema(s: pd.Series, span: int) -> pd.Series:
    """Exponential moving average."""
    return pd.to_numeric(s, errors="coerce").ewm(span=span, min_periods=span, adjust=False).mean()

def diff(s: pd.Series, periods: int = 1) -> pd.Series:
    """Difference."""
    return pd.to_numeric(s, errors="coerce").diff(periods=periods)

def atr_mid(s: pd.Series, window: int = 14, periods: int = 1) -> pd.Series:
    """ATR on spot"""
    return diff(s, periods).abs().rolling(window=window).mean()

def trend(s: pd.Series, periods: int = 1, window: int = 14) -> pd.Series:
    """ATR on spot"""
    return diff(s, periods).rolling(window=window).mean()

def rolling_mean(s: pd.Series, window: int) -> pd.Series:
    """Rolling mean (alias required by legacy pipeline)."""
    return pd.to_numeric(s, errors="coerce").rolling(window=window, min_periods=window).mean()

def rolling_std(s: pd.Series, window: int) -> pd.Series:
    """Rolling standard deviation (alias required by legacy pipeline)."""
    return pd.to_numeric(s, errors="coerce").rolling(window=window, min_periods=window).std()

def rolling_min(s: pd.Series, window: int) -> pd.Series:
    """Rolling minimum (legacy needed for reversals)."""
    return pd.to_numeric(s, errors="coerce").rolling(window=window, min_periods=window).min()

def rolling_max(s: pd.Series, window: int) -> pd.Series:
    """Rolling maximum (legacy needed for reversals)."""
    return pd.to_numeric(s, errors="coerce").rolling(window=window, min_periods=window).max()

def std_spread_logret(s: pd.Series, short_window: int, long_window: int) -> pd.Series:
    """
    spread = std_long(logret) - std_short(logret)
    """
    r = logret(s)
    v_short = r.rolling(int(short_window)).std()
    v_long  = r.rolling(int(long_window)).std()
    return v_long - v_short

def std_ratio_logret(s: pd.Series, short_window: int, long_window: int) -> pd.Series:
    """
    ratio = std_long(logret) / std_short(logret)
    """
    r = logret(s)
    v_short = r.rolling(int(short_window)).std()
    v_long  = r.rolling(int(long_window)).std()
    ratio = (v_short / v_long).replace([np.inf, -np.inf], np.nan).dropna()
    return ratio



# def test_features_combined_vol(s: pd.Series, price_series: Dict[str, pd.Series], key: str) -> pd.Series:
#     r1 = logret(s)
#     r2 = logret(price_series[key])

#     return









def zscore(s: pd.Series, window: int) -> pd.Series:
    """Rolling z-score."""
    x = pd.to_numeric(s, errors="coerce")
    mean = x.rolling(window=window, min_periods=window).mean()
    std = x.rolling(window=window, min_periods=window).std()
    return (x - mean) / std

def zscore_smooth_ewm(s: pd.Series, window: int, smooth_span: int) -> pd.Series:
    base = zscore(s, window)
    return base.ewm(span=smooth_span, min_periods=smooth_span, adjust=False).mean()

def rolling_vol(s: pd.Series, window: int) -> pd.Series:
    """Rolling volatility = std (historical alias kept)."""
    return rolling_std(s, window)

def rsi_wilder(s: pd.Series, window: int) -> pd.Series:
    """RSI with SMA averages."""
    x = pd.to_numeric(s, errors="coerce")
    delta = x.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)  
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()
    rs = avg_gain / (avg_loss+1e-12)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi

def rsi_ewm(s: pd.Series, window: int) -> pd.Series:
    """RSI with EWM averages."""
    delta = s.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(span=window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(span=window, min_periods=window, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-12)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi

def rsi_ewm_smooth(s: pd.Series, window: int, smooth_span: int) -> pd.Series:
    """RSI EWM then EWM smoothing."""
    base = rsi_ewm(s, window)
    return base.ewm(span=smooth_span, min_periods=smooth_span, adjust=False).mean()


# ---------- Stochastic Oscillator ----------

def stochastic_k(s: pd.Series, window: int = 14) -> pd.Series:
    """
    Stochastic %K (Fast Stochastic).
    
    %K = 100 * (Close - Lowest Low) / (Highest High - Lowest Low)
    
    Args:
        s: Price series (typically close prices)
        window: Lookback period for high/low (default 14)
    
    Returns:
        %K oscillator between 0 and 100
    """
    x = pd.to_numeric(s, errors="coerce")
    w = int(window)
    
    lowest_low = x.rolling(window=w, min_periods=w).min()
    highest_high = x.rolling(window=w, min_periods=w).max()
    
    denom = highest_high - lowest_low
    # Éviter division par zéro
    denom = denom.replace(0, np.nan)
    
    k = 100.0 * (x - lowest_low) / denom
    return k


def stochastic_d(s: pd.Series, k_window: int = 14, d_window: int = 3) -> pd.Series:
    """
    Stochastic %D (Slow Stochastic / Signal line).
    
    %D = SMA(%K, d_window)
    
    Args:
        s: Price series (typically close prices)
        k_window: Lookback period for %K calculation (default 14)
        d_window: SMA smoothing period for %D (default 3)
    
    Returns:
        %D oscillator between 0 and 100
    """
    k = stochastic_k(s, k_window)
    d = k.rolling(window=int(d_window), min_periods=int(d_window)).mean()
    return d


def stochastic_slow_k(s: pd.Series, k_window: int = 14, slow_window: int = 3) -> pd.Series:
    """
    Slow Stochastic %K.
    
    Slow %K = SMA(Fast %K, slow_window)
    
    C'est essentiellement le %D du stochastique rapide, mais utilisé comme %K lent.
    
    Args:
        s: Price series
        k_window: Lookback period for fast %K (default 14)
        slow_window: SMA smoothing period (default 3)
    
    Returns:
        Slow %K oscillator between 0 and 100
    """
    k_fast = stochastic_k(s, k_window)
    k_slow = k_fast.rolling(window=int(slow_window), min_periods=int(slow_window)).mean()
    return k_slow


def stochastic_slow_d(s: pd.Series, k_window: int = 14, slow_window: int = 3, d_window: int = 3) -> pd.Series:
    """
    Slow Stochastic %D.
    
    Slow %D = SMA(Slow %K, d_window)
    
    Args:
        s: Price series
        k_window: Lookback period for fast %K (default 14)
        slow_window: SMA smoothing for slow %K (default 3)
        d_window: SMA smoothing for slow %D (default 3)
    
    Returns:
        Slow %D oscillator between 0 and 100
    """
    k_slow = stochastic_slow_k(s, k_window, slow_window)
    d_slow = k_slow.rolling(window=int(d_window), min_periods=int(d_window)).mean()
    return d_slow


def stochastic_zscore(s: pd.Series, k_window: int = 14, zscore_window: int = 20) -> pd.Series:
    """
    Z-score du Stochastic %K.
    
    Utile pour normaliser le stochastique et l'utiliser comme signal mean-reversion.
    
    Args:
        s: Price series
        k_window: Lookback period for %K (default 14)
        zscore_window: Z-score rolling window (default 20)
    
    Returns:
        Z-scored stochastic (centered around 0)
    """
    k = stochastic_k(s, k_window)
    return zscore(k, zscore_window)


def stochastic_k_minus_d(s: pd.Series, k_window: int = 14, d_window: int = 3) -> pd.Series:
    """
    Différence entre %K et %D du stochastique.
    
    Utile pour détecter les croisements :
    - Quand %K - %D passe de négatif à positif → %K croise %D à la hausse (signal d'achat)
    - Quand %K - %D passe de positif à négatif → %K croise %D à la baisse (signal de vente)
    
    Args:
        s: Price series
        k_window: Lookback period for %K (default 14)
        d_window: SMA smoothing period for %D (default 3)
    
    Returns:
        %K - %D (peut être positif ou négatif, croisement à 0)
    """
    k = stochastic_k(s, k_window)
    d = k.rolling(window=int(d_window), min_periods=int(d_window)).mean()
    return k - d


def stochastic_slow_k_minus_d(s: pd.Series, k_window: int = 14, slow_window: int = 3, d_window: int = 3) -> pd.Series:
    """
    Différence entre Slow %K et Slow %D du stochastique lent.
    
    Version lissée pour moins de faux signaux.
    
    Args:
        s: Price series
        k_window: Lookback period for fast %K (default 14)
        slow_window: SMA smoothing for slow %K (default 3)
        d_window: SMA smoothing for slow %D (default 3)
    
    Returns:
        Slow %K - Slow %D
    """
    k_slow = stochastic_slow_k(s, k_window, slow_window)
    d_slow = k_slow.rolling(window=int(d_window), min_periods=int(d_window)).mean()
    return k_slow - d_slow



def shift(s: pd.Series, periods: int = 1) -> pd.Series:
    """Time shift."""
    return pd.to_numeric(s, errors="coerce").shift(int(periods))




# def get_slope(array) -> float:
#     """Slope of y over its index [0..len-1] — version 'rolling.apply' du code d'origine."""
#     y = np.array(array, dtype=float)
#     x = np.arange(len(y), dtype=float)
#     slope, intercept, _, _, _ = linregress(x, y)
#     return float(slope)


def rolling_slope(s: pd.Series, window: int) -> pd.Series:
    """
    Linear regression slope of y over x = [0..window-1] on a rolling window,
    EXACTLY matching: linregress(x, y).slope used in your legacy `get_slope`.

    - NaN if the window contains any NaN (same behavior as a rolling apply of linregress).
    - No normalization on y; x is the integer index 0..w-1 at each window.
    """
    x = np.arange(int(window), dtype=float)
    w = int(window)
    x_sum = x.sum()
    x2_sum = (x * x).sum()
    denom = w * x2_sum - (x_sum * x_sum)
    if w <= 1 or denom == 0.0:
        # not enough points or degenerate window
        return pd.Series(np.nan, index=s.index, name=s.name)

    y = pd.to_numeric(s, errors="coerce").values.astype(float)
    n = len(y)
    out = np.full(n, np.nan, dtype=float)

    for i in range(w - 1, n):
        win = y[i - w + 1 : i + 1]
        if not np.isfinite(win).all():
            # mimic linregress on bad data: return NaN
            continue
        y_sum = win.sum()
        xy_sum = (x * win).sum()
        slope = (w * xy_sum - x_sum * y_sum) / denom
        out[i] = float(slope)

    return pd.Series(out, index=s.index, name=s.name)


def reversal_up(close: pd.Series, window: int) -> pd.Series:

    c = pd.to_numeric(close, errors="coerce")
    c_1 = c.shift(1)
    c_2 = c.shift(2)
    roll_min = c_1.rolling(window=int(window), min_periods=int(window)).min()
    cond = (c_2 == roll_min.shift(1)) & (c_1 > c_2)
    return cond.astype(float)

def reversal_down(close: pd.Series, window: int) -> pd.Series:

    c = pd.to_numeric(close, errors="coerce")
    c_1 = c.shift(1)
    c_2 = c.shift(2)
    roll_max = c_1.rolling(window=int(window), min_periods=int(window)).max()
    cond = (c_2 == roll_max.shift(1)) & (c_1 < c_2)
    return cond.astype(float)





def sum_spot_fut_shifted(
    spot: pd.Series, 
    fut: pd.Series, 
    shift_fut: int = 1,
    weights: tuple = (1.0, 1.0)
) -> pd.Series:

    shifted_fut = fut.shift(shift_fut) # if shift_fut != 0 else fut
    w_spot, w_fut = weights
    return w_spot * spot + w_fut * shifted_fut


def zscore_combined_spot_fut(
    spot: pd.Series,
    fut_key: str,
    shift_fut: int = 1,
    window_spot: int = 20,
    window_fut: int = 20,
    optional_time_series: Optional[Dict[str, pd.Series]] = None
) -> pd.Series:

    if optional_time_series is None or fut_key not in optional_time_series:
        raise ValueError(f"Missing '{fut_key}' in optional_time_series for zscore_combined_spot_fut")
    
    fut = optional_time_series[fut_key]
    fut_shifted = fut.shift(shift_fut)
    
    z_spot = zscore(spot, window_spot)
    z_fut = zscore(fut_shifted, window_fut)
    
    return 0.5 * (z_spot + z_fut)





# ---------- Registry (name -> callable) ----------

TRANSFORMS: Dict[str, Callable[..., pd.Series]] = {
    
    "identity": lambda s: identity(s),
    "returns": lambda s: returns(s),
    "inv": lambda s: inv(s),
    "mult": lambda s, coeff=1: mult(s, coeff),
    "add": lambda s, amount=1: add(s, amount),


    "logret": lambda s, periods=1: logret(s, int(periods)),
    "ratio_stds": lambda s, short_window=126, long_window=252: std_ratio_logret(s, int(short_window), int(long_window)),
    "spread_stds": lambda s, short_window=126, long_window=252: std_spread_logret(s, int(short_window), int(long_window)),

    "sma": lambda s, window: sma(s, int(window)),
    "ema": lambda s, span: ema(s, int(span)),
    "diff": lambda s, periods=1: diff(s, int(periods)),
    "shift": lambda s, periods=1: shift(s, int(periods)),
    "rolling_mean": lambda s, window: rolling_mean(s, int(window)),
    "rolling_std": lambda s, window: rolling_std(s, int(window)),
    "rolling_min": lambda s, window: rolling_min(s, int(window)),
    "rolling_max": lambda s, window: rolling_max(s, int(window)),
    "rolling_slope": lambda s, window: rolling_slope(s, int(window)),
    "atr_mid": lambda s, window, periods=1: atr_mid(s, int(window), int(periods)),
    "trend": lambda s, window, periods=1: trend(s, int(periods), int(window)),

    "zscore": lambda s, window: zscore(s, int(window)),
    "zscore_smooth_ewm": lambda s, window, smooth_span: zscore_smooth_ewm(s, int(window), int(smooth_span)),
    "rolling_vol": lambda s, window: rolling_vol(s, int(window)),

    "rsi": lambda s, window: rsi_wilder(s, int(window)),  
    "rsi_ewm": lambda s, window: rsi_ewm(s, int(window)),
    "rsi_ewm_smooth": lambda s, window, smooth_span: rsi_ewm_smooth(s, int(window), int(smooth_span)),

    # Stochastic Oscillator
    "stochastic_k": lambda s, window=14: stochastic_k(s, int(window)),
    "stochastic_d": lambda s, k_window=14, d_window=3: stochastic_d(s, int(k_window), int(d_window)),
    "stochastic_slow_k": lambda s, k_window=14, slow_window=3: stochastic_slow_k(s, int(k_window), int(slow_window)),
    "stochastic_slow_d": lambda s, k_window=14, slow_window=3, d_window=3: stochastic_slow_d(s, int(k_window), int(slow_window), int(d_window)),
    "stochastic_zscore": lambda s, k_window=14, zscore_window=20: stochastic_zscore(s, int(k_window), int(zscore_window)),
    "stochastic_k_minus_d": lambda s, k_window=14, d_window=3: stochastic_k_minus_d(s, int(k_window), int(d_window)),
    "stochastic_slow_k_minus_d": lambda s, k_window=14, slow_window=3, d_window=3: stochastic_slow_k_minus_d(s, int(k_window), int(slow_window), int(d_window)),

    "reversal_up": lambda s, window: reversal_up(s, int(window)),
    "reversal_down": lambda s, window: reversal_down(s, int(window)),
    "sum_spot_fut_shifted": lambda spot, fut, shift_fut=1, weights=(1.0, 1.0): sum_spot_fut_shifted(spot, fut, shift_fut, weights),
    "zscore_combined_spot_fut": lambda spot, fut_key, shift_fut=1, window_spot=20, window_fut=20, optional_time_series=None: zscore_combined_spot_fut(spot, fut_key, int(shift_fut), int(window_spot), int(window_fut), optional_time_series)
}


def apply_ops(series: pd.Series, ops: list, optional_time_series: Optional[Dict[str, pd.Series]]) -> pd.Series:
    """Apply a list of ops from TRANSFORMS registry (look-ahead safe: no ffill here)."""
    # out = pd.to_numeric(series, errors="coerce")
    # for op in ops:
    #     name = op.get("op")
    #     if name not in TRANSFORMS:
    #         raise ValueError(f"Unknown transform '{name}'")
    #     params = {k: v for k, v in op.items() if k != "op"}
    #     out = TRANSFORMS[name](out, **params)
    # return out

    result = series
    for op_spec in ops:
        op_name = op_spec.get("op")
        if op_name not in TRANSFORMS:
            raise KeyError(f"Unknown transform: {op_name}")
        
        fn = TRANSFORMS[op_name]
        kwargs = {k: v for k, v in op_spec.items() if k != "op"}
        
        # Passer optional_time_series pour les ops qui la demandent
        if op_name in ["sum_spot_fut_shifted", "zscore_combined_spot_fut"] and optional_time_series is not None:
            kwargs["optional_time_series"] = optional_time_series
        
        result = fn(result, **kwargs)
    
    return result