def _register_all_profiles():
   
    # zscore cash sb11 (spread)
    # zscore futures shifted robusta (vtm)
    # zscore futures shifted arabica (brazil GC)
    from .usecases_profiles.coffee_profiles import (
        arabica_zscore_fut_shifted_wf,
        robusta_zscore_fut_shifted_wf,
    )

    # RSI futures shifted sb11
    # zscore futures shifted sb11
    # RSI cash sb11 (spread)
    from .usecases_profiles.sugar_profiles import (
        sb11_rsi_fut_shifted,
        sb11_rsi_wf,
        sb11_wf,
        sb11_zscore_fut_shifted,
    )




# Auto-register au chargement
_register_all_profiles()