from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Dict, List, Tuple

# --------------------------------------------------------------------------------------
# Path syntax (générique, sans cas spéciaux):
#   <root>.<seg>.<seg>...
# Seg peut être:
#   - un identifiant dict/attr:   "recipes", "cfg", "params"
#   - un index de liste:          "ops[0]"
#   - un selecteur dans une liste: "ops[op=zscore]"  (match item["op"] == "zscore")
#   - une clé dict explicite:     "recipes[key=ZS]"  (match recipes["ZS"] si c'est un dict de dicts)
#
# Exemples:
#   normalizer.low
#   risk.enabled
#   risk.rules[type=sl_pct].params.pct
#   sizer.steps[service=constant].cfg.value
#   input_spec.recipes[key=zscore20_smooth_ewm9].ops[op=zscore_smooth_ewm].window
#
# Le binder:
#   1) matérialise une vue mutable des sous-objets top-level
#   2) applique tous les patches (chemin -> valeur) via _path_set
#   3) reconstruit seulement les blocs top-level touchés (classes connues)
#   4) retourne overrides + applied/unknown pour le mode strict
# --------------------------------------------------------------------------------------

_seg_re = re.compile(r"""
    (?P<name>[A-Za-z_]\w*)                      # nom du segment (dict key ou attr)
    (?:\[(?P<sel>[^=\]]+)(?:=(?P<val>[^\]]+))?\])?   # selecteur optionnel: [index] | [key] | [key=value]
""", re.X)

def _deep_copy_cfg(obj: Any) -> Any:
    # objets config simples -> dict via __dict__, sinon deepcopy
    if hasattr(obj, "__dict__"):
        d = {}
        for k, v in obj.__dict__.items():
            d[k] = deepcopy(v)
        return d
    return deepcopy(obj)

def _path_parse(path: str) -> List[Tuple[str, str|None, str|None]]:
    out: List[Tuple[str, str|None, str|None]] = []
    for raw in path.split("."):
        m = _seg_re.fullmatch(raw)
        if not m:
            raise ValueError(f"Invalid segment in path: {raw}")
        name, sel, val = m.group("name", "sel", "val")
        out.append((name, sel, val))
    return out

def _sel_resolve(container: Any, name: str, sel: str, val: str|None) -> Tuple[Any, Any]:
    """
    Retourne (parent, ref) où 'ref' est l'élément ciblé sous container[name][selector].
    Supporte:
      - liste par index: [3]
      - liste par selecteur clé=val: [op=zscore], [service=constant]
      - dict par clé: [key=ZZ] => container[name]["ZZ"]
    """
    tgt = container[name]
    # index
    if sel.isdigit():
        idx = int(sel)
        if isinstance(tgt, list):
            # extend list si besoin
            while len(tgt) <= idx:
                tgt.append({})
            return (tgt, tgt[idx])
        raise KeyError(f"Selector [{sel}] not a list on segment '{name}'")
    # clef unique sans valeur: [key] => dict direct
    if val is None and isinstance(tgt, dict):
        # ex: recipes[key] -> on retourne ce dict pour suite
        return (container, tgt)
    # key=value
    key = sel
    if isinstance(tgt, list):
        for it in tgt:
            if isinstance(it, dict) and it.get(key) == val:
                return (tgt, it)
        # si non trouvé: on crée un dict conforme pour ce selecteur
        new_it = {key: val}
        tgt.append(new_it)
        return (tgt, new_it)
    if isinstance(tgt, dict):
        # ex: recipes[key=ZS] => recipes["ZS"]
        if key == "key":
            k = val
            if k not in tgt:
                tgt[k] = {}
            return (tgt, tgt[k])
    raise KeyError(f"Unsupported selector on '{name}[{sel}={val}]'")

def _path_set(root: Dict[str, Any], path: str, value: Any) -> bool:
    """
    Applique path -> value dans 'root'. Retourne True si appliqué, False sinon.
    """
    try:
        segs = _path_parse(path)
    except Exception:
        return False

    cur = root
    parents: List[Tuple[Any, str|int]] = []
    for i, (name, sel, sval) in enumerate(segs):
        is_last = (i == len(segs) - 1)

        # accède / crée le segment
        if name not in cur:
            # pour un dernier segment, créer clé simple
            cur[name] = {} if not is_last else None
        if sel is None:
            # dict or attr-like
            if is_last:
                cur[name] = value
                return True
            if not isinstance(cur[name], (dict, list)):
                # on écrase par un dict pour descendre
                cur[name] = {}
            parents.append((cur, name))
            cur = cur[name]
        else:
            # avec selecteur
            parent, ref = _sel_resolve(cur, name, sel, sval)
            if is_last:
                if isinstance(parent, list):
                    # 'ref' est un dict: on set dans ref, mais on accepte aussi une affectation simple
                    if isinstance(ref, dict):
                        # on exige une clé (ex: field) sur le prochain segment => mais on est last: on ne sait pas quelle field
                        # donc on remonte: valeur posée sur ref["value"]
                        ref["value"] = value
                    else:
                        idx = parent.index(ref)
                        parent[idx] = value
                elif isinstance(parent, dict) and isinstance(ref, dict):
                    # idem: on set ref["value"]
                    ref["value"] = value
                else:
                    # cas simple: parent[name] = value (rare ici)
                    cur[name] = value
                return True
            else:
                # on descend dans ref
                if not isinstance(ref, (dict, list)):
                    # convertir en dict pour pouvoir descendre
                    ref = {}
                    if isinstance(parent, list):
                        # remplace l'item
                        for j, it in enumerate(parent):
                            if it is ref:
                                parent[j] = ref
                                break
                cur = ref
    return False

# --------------------------------------------------------------------------------------




from mvc_core.strategies.components.features.feature_data import InputSpec
from mvc_core.strategies.components.risk.risk_data import RiskConfig
from mvc_core.strategies.components.sizers.sizer_data import SizerConfig
from mvc_core.strategies.core.strategy_data import StrategyCfg, StrategyComponents


def bind_params(params: Dict[str, Any], base_cfg: StrategyCfg) -> Dict[str, Any]:
    """
    Binder compatible StrategyCfg.
    - params: dictionnaire { "normalizer.low": 0.5, "source.ops[0].window": 20, ... }
    - base_cfg: StrategyCfg de base (non modifié)
    Retourne:
    {
        "strategy_cfg": StrategyCfg(...),
        "__applied_keys__": [...],
        "__unknown_keys__": [...],
    }
    """



    applied: set[str] = set()
    work: Dict[str, Any] = {}
    touched: set[str] = set()

    # 1) extraire les objets de config depuis StrategyCfg
    normalizer = getattr(base_cfg, "normalizer_cfg", None)
    source = getattr(base_cfg, "source_cfg", None)
    risk = getattr(base_cfg, "risk_cfg", None)
    sizer = getattr(base_cfg, "sizer_cfg", None)
    spec = getattr(base_cfg, "input_spec", None)

    # eventuel signalizer dans extras (si tu l'utilises)
    signalizer = None
    if isinstance(base_cfg.extras, dict):
        signalizer = base_cfg.extras.get("signalizer_cfg", None)

    # 1bis) remplir le dict de travail "work" à partir des objets existants
    if normalizer is not None:
        work["normalizer"] = _deep_copy_cfg(normalizer)

    if source is not None:
        work["source"] = _deep_copy_cfg(source)

    if risk is not None:
        work["risk"] = _deep_copy_cfg(risk)

    if sizer is not None:
        work["sizer"] = _deep_copy_cfg(sizer)

    if signalizer is not None:
        work["signalizer"] = _deep_copy_cfg(signalizer)

    if spec is not None:
        work["input_spec"] = {
            "base_keys": deepcopy(getattr(spec, "base_keys", {})),
            "recipes": deepcopy(getattr(spec, "recipes", {})),
            "extras": deepcopy(getattr(spec, "extras", {})),
        }

    # 2) appliquer les params via _path_set
    for k, v in params.items():
        root = k.split(".", 1)[0]
        if root not in work:
            # racine inconnue => on traitera ça comme param non appliqué
            continue
        ok = _path_set(work, k, v)
        if ok:
            applied.add(k)
            touched.add(root)

    # 3) reconstruire les blocs touchés depuis 'work'
    new_normalizer = normalizer
    new_source = source
    new_risk = risk
    new_sizer = sizer
    new_signalizer = signalizer
    new_spec = spec

    if "normalizer" in touched and normalizer is not None:
        cls = type(normalizer)
        new_normalizer = cls(**work["normalizer"])

    if "source" in touched and source is not None:
        cls = type(source)
        new_source = cls(**work["source"])

    if "risk" in touched and risk is not None:
        new_risk = RiskConfig(**work["risk"])

    if "sizer" in touched and sizer is not None:

        new_sizer = SizerConfig(**work["sizer"])

    if "signalizer" in touched and signalizer is not None:
        cls = type(signalizer)
        new_signalizer = cls(**work["signalizer"])

    if "input_spec" in touched and spec is not None:
        w = work["input_spec"]
        new_spec = InputSpec(
            base_keys=w["base_keys"],
            recipes=w["recipes"],
            extras=w["extras"],
        )

    if isinstance(base_cfg.extras, dict):
        new_extras = deepcopy(base_cfg.extras)
    else:
        new_extras = {}

    if "signalizer" in touched and new_signalizer is not None:
        new_extras["signalizer_cfg"] = new_signalizer


    new_components = StrategyComponents(
        source_fn=base_cfg.components.source_fn if base_cfg.components else None,
        normalizer_fn=base_cfg.components.normalizer_fn if base_cfg.components else None,
        # on ne modifie pas sizer_fn / risk_fn / signalizer_fn ici (ils seront construits dans build_runtime_strategy)
    )
    # 5) construire le nouveau StrategyCfg
    new_strategy = StrategyCfg(
        instrument=base_cfg.instrument,
        input_spec=new_spec if new_spec is not None else base_cfg.input_spec,
        source_cfg=new_source if new_source is not None else base_cfg.source_cfg,
        normalizer_cfg=new_normalizer if new_normalizer is not None else base_cfg.normalizer_cfg,
        sizer_cfg=new_sizer if new_sizer is not None else base_cfg.sizer_cfg,
        risk_cfg=new_risk if new_risk is not None else base_cfg.risk_cfg,
        components=new_components,
        # source_fn=base_cfg.components.source_fn,
        # normalizer_fn=base_cfg.components.normalizer_fn,
        extras=new_extras,
    )

    # 6) mode strict: on expose les clés appliquées et inconnues
    overrides: Dict[str, Any] = {}
    overrides["strategy_cfg"] = new_strategy
    overrides["__applied_keys__"] = sorted(applied)
    overrides["__unknown_keys__"] = sorted(set(params.keys()) - applied)
    return overrides





def bind_params_v2(params: Dict[str, Any], base_cfg: StrategyCfg) -> Dict[str, Any]:
    """
    Binder compatible StrategyCfg.
    - params: dictionnaire { "normalizer.low": 0.5, "source.ops[0].window": 20, ... }
    - base_cfg: StrategyCfg de base (non modifié)
    Retourne:
    {
        "strategy_cfg": StrategyCfg(...),
        "__applied_keys__": [...],
        "__unknown_keys__": [...],
    }
    """



    applied: set[str] = set()
    work: Dict[str, Any] = {}
    touched: set[str] = set()

    # 1) extraire les objets de config depuis StrategyCfg
    normalizer = getattr(base_cfg, "normalizer_cfg", None)
    source = getattr(base_cfg, "source_cfg", None)
    risk = getattr(base_cfg, "risk_cfg", None)
    sizer = getattr(base_cfg, "sizer_cfg", None)
    spec = getattr(base_cfg, "input_spec", None)

    # eventuel signalizer dans extras (si tu l'utilises)
    signalizer = None
    if isinstance(base_cfg.extras, dict):
        signalizer = base_cfg.extras.get("signalizer_cfg", None)

    # 1bis) remplir le dict de travail "work" à partir des objets existants
    if normalizer is not None:
        work["normalizer"] = _deep_copy_cfg(normalizer)

    if source is not None:
        work["source"] = _deep_copy_cfg(source)

    if risk is not None:
        work["risk"] = _deep_copy_cfg(risk)

    if sizer is not None:
        work["sizer"] = _deep_copy_cfg(sizer)

    if signalizer is not None:
        work["signalizer"] = _deep_copy_cfg(signalizer)

    if spec is not None:
        work["input_spec"] = {
            "base_keys": deepcopy(getattr(spec, "base_keys", {})),
            "recipes": deepcopy(getattr(spec, "recipes", {})),
            "extras": deepcopy(getattr(spec, "extras", {})),
        }

    # 2) appliquer les params via _path_set
    for k, v in params.items():
        root = k.split(".", 1)[0]
        if root not in work:
            # racine inconnue => on traitera ça comme param non appliqué
            continue
        ok = _path_set(work, k, v)
        if ok:
            applied.add(k)
            touched.add(root)

    # 3) reconstruire les blocs touchés depuis 'work'
    new_normalizer = normalizer
    new_source = source
    new_risk = risk
    new_sizer = sizer
    new_signalizer = signalizer
    new_spec = spec

    if "normalizer" in touched and normalizer is not None:
        cls = type(normalizer)
        new_normalizer = cls(**work["normalizer"])

    if "source" in touched and source is not None:
        cls = type(source)
        new_source = cls(**work["source"])

    if "risk" in touched and risk is not None:
        new_risk = RiskConfig(**work["risk"])

    if "sizer" in touched and sizer is not None:

        new_sizer = SizerConfig(**work["sizer"])

    if "signalizer" in touched and signalizer is not None:
        cls = type(signalizer)
        new_signalizer = cls(**work["signalizer"])

    if "input_spec" in touched and spec is not None:
        w = work["input_spec"]
        new_spec = InputSpec(
            base_keys=w["base_keys"],
            recipes=w["recipes"],
            extras=w["extras"],
        )

    if isinstance(base_cfg.extras, dict):
        new_extras = deepcopy(base_cfg.extras)
    else:
        new_extras = {}

    if "signalizer" in touched and new_signalizer is not None:
        new_extras["signalizer_cfg"] = new_signalizer


    new_components = StrategyComponents(
        source_fn=base_cfg.components.source_fn if base_cfg.components else None,
        normalizer_fn=base_cfg.components.normalizer_fn if base_cfg.components else None,
        # on ne modifie pas sizer_fn / risk_fn / signalizer_fn ici (ils seront construits dans build_runtime_strategy)
    )
    # 5) construire le nouveau StrategyCfg
    new_strategy = StrategyCfg(
        instrument=base_cfg.instrument,
        input_spec=new_spec if new_spec is not None else base_cfg.input_spec,
        source_cfg=new_source if new_source is not None else base_cfg.source_cfg,
        normalizer_cfg=new_normalizer if new_normalizer is not None else base_cfg.normalizer_cfg,
        sizer_cfg=new_sizer if new_sizer is not None else base_cfg.sizer_cfg,
        risk_cfg=new_risk if new_risk is not None else base_cfg.risk_cfg,
        components=new_components,
        # source_fn=base_cfg.components.source_fn,
        # normalizer_fn=base_cfg.components.normalizer_fn,
        extras=new_extras,
    )

    # 6) mode strict: on expose les clés appliquées et inconnues
    overrides: Dict[str, Any] = {}
    overrides["strategy_cfg"] = new_strategy
    overrides["__applied_keys__"] = sorted(applied)
    overrides["__unknown_keys__"] = sorted(set(params.keys()) - applied)
    return overrides