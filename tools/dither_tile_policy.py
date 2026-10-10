"""Black Tiger MD - regras de dithering por codigo e fase.

Este modulo e compartilhado entre extract.py e Dithering Lab 2.0.
A conversao customizada utiliza a MESMA funcao convert_adaptive do projeto,
com apenas seis constantes numericas substituidas em memoria.
"""
from __future__ import annotations
import ast
import inspect
import json
from pathlib import Path
import re

import dither_bg

MODES = ('original', 'bayer4', 'bayer4_soft', 'bayer4_adaptive')
POLICIES = ('inherit', *MODES)
PARAMS = (
    ('min_error', 'Erro mínimo RGB²', 0.5, 0.0, 5.0, 0.05),
    ('max_distance', 'Distância máxima RGB²', 20.0, 2.0, 50.0, 0.5),
    ('max_luma', 'Diferença máxima de luminância', 2.3, 0.0, 6.0, 0.1),
    ('contrast_penalty', 'Penalização de contraste', 0.04, 0.0, 0.25, 0.005),
    ('min_score', 'Ganho mínimo', 0.25, 0.0, 3.0, 0.05),
    ('max_mix', 'Mistura máxima (%)', 48.0, 0.0, 80.0, 1.0),
)
DEFAULTS = {k: d for k, _, d, _, _, _ in PARAMS}

# BLACKTIGER_MULTIMODE_SLIDERS_V1
# Controles de cada algoritmo — os valores padrao reproduzem o modulo original.
# Lista: (chave, descricao, valor padrao, minimo, maximo, passo)
MODE_PARAMS = {
    'original': (),
    'bayer4': (
        ('strength', 'Intensidade Bayer (%)', 100.0, 0.0, 100.0, 1.0),
    ),
    'bayer4_soft': (
        ('strength', 'Intensidade Bayer (%)', 100.0, 0.0, 100.0, 1.0),
        ('density', 'Limite da matriz Bayer', 9.0, 0.0, 16.0, 1.0),
        ('min_error', 'Erro minimo RGB²', 1.0, 0.0, 8.0, 0.25),
        ('max_luma', 'Diferenca max. luminancia', 2.0, 0.0, 5.0, 0.1),
        ('max_chroma', 'Diferenca max. de cor', 3.5, 0.0, 10.0, 0.1),
    ),
    'bayer4_adaptive': PARAMS,
}
MODE_DEFAULTS = {mode:{row[0]:row[2] for row in rows} for mode,rows in MODE_PARAMS.items()}
MODE_HELP = {
    'bayer4': {
        'strength': ('Proporcao da segunda cor no Bayer 4x4. 100% corresponde ao Bayer4 '
                     'original. Menor intensidade produz menos pontos da segunda cor; '
                     '0% deixa apenas a cor mais proxima (nao necessariamente o mapeamento original).'),
    },
    'bayer4_soft': {
        'strength': 'Controla a intensidade das propostas do Bayer antes do filtro balanced.',
        'density': ('Quantos dos 16 pontos da matriz Bayer podem aceitar substituicoes. '
                    '9 reproduz o Balanced atual; 0 suprime todas as substituicoes.'),
        'min_error': ('Erro minimo de quantizacao para admitir mistura. '
                      'Menor valor permite mais regioes.'),
        'max_luma': ('Diferenca permitida de brilho entre a cor mapeada e a proposta. '
                     'Maior valor aceita contrastes mais intensos.'),
        'max_chroma': ('Distancia RGB333 maxima entre duas cores. '
                       'Maior valor permite cores mais distantes.'),
    },
}


def mode_defaults(mode):
    if mode not in MODE_DEFAULTS:
        raise ValueError('Modo de conversao invalido: '+str(mode))
    return dict(MODE_DEFAULTS[mode])


def validate_mode_params(mode, params):
    if mode not in MODE_PARAMS or mode == 'original':
        raise ValueError('Nao existem parametros para o modo '+str(mode))
    if mode == 'bayer4_adaptive':
        return validate_params(params)
    if not isinstance(params, dict):
        raise ValueError('Parametros devem formar um objeto JSON')
    definitions=MODE_PARAMS[mode]
    expected={row[0] for row in definitions}
    if set(params)!=expected:
        raise ValueError('Parametros de '+mode+' devem conter '+', '.join(sorted(expected)))
    result={}
    import math
    for key,_,_,low,high,_ in definitions:
        raw=params[key]
        if isinstance(raw,bool):
            raise ValueError('Booleano invalido para '+key)
        value=float(raw)
        if not math.isfinite(value) or not low<=value<=high:
            raise ValueError(f'{mode}.{key} fora do intervalo {low}..{high}')
        result[key]=round(value,6)
    return result


def bayer4_custom(indices, source_palette, target_palette, params):
    validated=validate_mode_params('bayer4',params)
    return dither_bg.convert(indices,source_palette,target_palette,
                             strength=validated['strength']/100.0)


def soft_custom(indices, source_palette, target_palette, original_mapping, params):
    # Replica convert_soft() do projeto, com filtros parametrizados.
    # Os valores default foram comparados com a funcao original.
    import numpy as np
    v=validate_mode_params('bayer4_soft',params)
    indices=np.asarray(indices,dtype=np.uint8)
    target=np.asarray(target_palette,dtype=np.float64)
    source=np.asarray(source_palette,dtype=np.float64)
    mapping=np.asarray(original_mapping,dtype=np.uint8)
    base=mapping[indices].copy()
    proposed=dither_bg.convert(indices,source_palette,target_palette,
                               strength=v['strength']/100.0)
    if proposed.shape!=base.shape:
        proposed=proposed.reshape(base.shape)
    bayer=dither_bg.BAYER4
    yy,xx=np.indices(base.shape[-2:])
    sparse=bayer[yy%4,xx%4]<v['density']
    dist=np.sum((source[:,None,:]-target[None,:,:])**2,axis=2)
    error=np.min(dist,axis=1)[indices]>=v['min_error']
    safe=(base>0)&(proposed>0)&(proposed<=len(target))
    base_idx=np.clip(base.astype(int)-1,0,len(target)-1)
    prop_idx=np.clip(proposed.astype(int)-1,0,len(target)-1)
    weights=np.array([0.2126,0.7152,0.0722])
    delta=np.abs((target[base_idx]-target[prop_idx]) @ weights)
    chroma=np.linalg.norm(target[base_idx]-target[prop_idx],axis=-1)
    keep=(proposed!=base)&sparse&error&safe&(delta<=v['max_luma'])&(chroma<=v['max_chroma'])
    base[keep]=proposed[keep]
    return base


def render_custom_mode(mode, indices, source_palette, target_palette, original_mapping, params):
    if mode=='bayer4':
        return bayer4_custom(indices,source_palette,target_palette,params)
    if mode=='bayer4_soft':
        return soft_custom(indices,source_palette,target_palette,original_mapping,params)
    if mode=='bayer4_adaptive':
        return adaptive_custom(indices,source_palette,target_palette,original_mapping,params)
    raise ValueError('Modo sem parametros editaveis: '+str(mode))
LIMITS = {k: (lo, hi) for k, _, _, lo, hi, _ in PARAMS}
REPLACEMENTS = (
    (r'if original_error\s*<\s*[\d.]+\s*:', 'if original_error < {min_error}:'),
    (r'if norm2\s*<\s*1e-8\s+or\s+norm2\s*>\s*[\d.]+\s*:', 'if norm2 < 1e-8 or norm2 > {max_distance}:'),
    (r'if abs\(float\(np\.dot\(direction, weights\)\)\)\s*>\s*[\d.]+\s*:', 'if abs(float(np.dot(direction, weights))) > {max_luma}:'),
    (r'np\.clip\(np\.dot\(color - first, direction\) / norm2, 0\.0,\s*[\d.]+\)', 'np.clip(np.dot(color - first, direction) / norm2, 0.0, {max_mix_fraction})'),
    (r'score\s*=\s*gain\s*-\s*[\d.]+\s*\*\s*norm2', 'score = gain - {contrast_penalty} * norm2'),
    (r'if best_index\s*>=\s*0\s+and\s+best_score\s*>=\s*[\d.]+\s*:', 'if best_index >= 0 and best_score >= {min_score}:'),
)


def validate_params(params):
    if not isinstance(params, dict):
        raise ValueError('Os parametros de dithering devem ser um objeto JSON.')
    if set(params) != set(DEFAULTS):
        raise ValueError('Os parametros personalizados devem conter exatamente: ' + ', '.join(DEFAULTS))
    result = {}
    for name in DEFAULTS:
        v = params[name]
        if isinstance(v, bool):
            raise ValueError('Valor booleano invalido: ' + name)
        v = float(v)
        low, high = LIMITS[name]
        if not low <= v <= high:
            raise ValueError(f'{name} fora dos limites: {v} (esperado {low}..{high})')
        result[name] = round(v, 6)
    return result


def normalize_rules(data):
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('tile_dither_rules.json precisa ter version=1')
    stages = data.get('stages', {})
    if not isinstance(stages, dict):
        raise ValueError('stages precisa ser um objeto')
    out = {'version': 1, 'stages': {str(i): {} for i in range(8)}}
    for s, rules in stages.items():
        if str(s) not in out['stages'] or not isinstance(rules, dict):
            raise ValueError('Fase invalida no JSON: ' + str(s))
        for code_str, rule in rules.items():
            try:
                code = int(code_str)
            except ValueError as exc:
                raise ValueError('Codigo de tile invalido: ' + str(code_str)) from exc
            if not 0 <= code < 2048 or not isinstance(rule, dict):
                raise ValueError('Regra invalida para tile ' + str(code))
            mode = rule.get('mode')
            if mode not in POLICIES:
                raise ValueError('Modo invalido: ' + str(mode))
            if mode == 'inherit':
                continue
            val = {'mode': mode}
            if 'parameters' in rule:
                val['parameters'] = validate_mode_params(mode, rule['parameters'])
            if 'palette_overrides' in rule:
                if mode == 'original':
                    raise ValueError('O modo original nao aceita mistura manual')
                val['palette_overrides'] = validate_palette_overrides(rule['palette_overrides'])
            out['stages'][str(s)][str(code)] = val
    return out


def load_all(path):
    path = Path(path)
    if not path.is_file():
        return {'version': 1, 'stages': {str(i): {} for i in range(8)}}
    return normalize_rules(json.loads(path.read_text(encoding='utf-8')))


def load_stage(path, stage):
    return {int(c): rule for c, rule in load_all(path)['stages'][str(stage)].items()}


def render_adaptive_source(params):
    values = validate_params(params)
    values['max_mix_fraction'] = round(values['max_mix'] / 100.0, 6)
    source = inspect.getsource(dither_bg.convert_adaptive)
    for pattern, template in REPLACEMENTS:
        source, n = re.subn(pattern, template.format(**values), source)
        if n != 1:
            raise RuntimeError(f'Algoritmo adaptativo mudou: {n} substituicoes para {pattern}.')
    ast.parse(source)
    return source


_cached = {}

def adaptive_custom(indices, source_palette, target_palette, original_mapping, parameters):
    params = validate_params(parameters)
    # Cache seguro por parametros + texto-fonte do algoritmo vigente nesta compilacao.
    raw = inspect.getsource(dither_bg.convert_adaptive)
    key = (raw, tuple(params[k] for k in DEFAULTS))
    if key not in _cached:
        if len(_cached) > 40:
            _cached.clear()
        scope = dict(dither_bg.__dict__)
        exec(compile(render_adaptive_source(params), '<blacktiger-adaptive-custom>', 'exec'), scope)
        _cached[key] = scope['convert_adaptive']
    return _cached[key](indices, source_palette, target_palette, original_mapping)

# BLACKTIGER_PALETTE_EDITOR_V1
# Um par de cores e atribuido a um PEN DE ORIGEM especifico de uma paleta
# especifica. Nunca se substitui o conjunto inteiro de cores de um tile.
# Estrutura: palette_overrides = {"6":{"3":{"secondary":5,"mix":35.0}}}
# Indices de destino: 1..15; indice 0 reservado para transparencia.

def validate_palette_overrides(data):
    import math
    if not isinstance(data, dict):
        raise ValueError('palette_overrides precisa ser um objeto JSON')
    cleaned={}
    for palette, pens in data.items():
        try:
            p=int(palette)
        except (TypeError, ValueError) as exc:
            raise ValueError('Paleta de origem invalida: '+str(palette)) from exc
        if str(p)!=str(palette) or not 0<=p<=15 or not isinstance(pens,dict):
            raise ValueError('Paleta de origem deve ser um indice 0..15')
        records={}
        for pen, entry in pens.items():
            try:
                source_pen=int(pen)
            except (TypeError, ValueError) as exc:
                raise ValueError('Pen de origem invalido: '+str(pen)) from exc
            if str(source_pen)!=str(pen) or not 0<=source_pen<=15 or not isinstance(entry,dict):
                raise ValueError('Pen de origem deve ser indice 0..15')
            if set(entry) not in ({'secondary','mix'}, {'primary','secondary','mix'}):
                raise ValueError('Par manual requer secondary, mix e primary opcional')
            secondary=entry['secondary']
            if type(secondary) is not int or not 1<=secondary<=15:
                raise ValueError('Cor secundaria deve estar entre 1 e 15')
            result={'secondary':secondary}
            if 'primary' in entry:
                primary=entry['primary']
                if type(primary) is not int or not 1<=primary<=15:
                    raise ValueError('Cor primaria deve estar entre 1 e 15')
                result['primary']=primary
            mixing=entry['mix']
            if isinstance(mixing,bool):
                raise ValueError('Porcentagem de mistura nao pode ser booleana')
            try:
                mixing=float(mixing)
            except (ValueError,TypeError) as exc:
                raise ValueError('Porcentagem de mistura invalida') from exc
            if not math.isfinite(mixing) or not 0<=mixing<=100:
                raise ValueError('Porcentagem de mistura deve estar entre 0 e 100')
            result['mix']=round(mixing,3)
            records[str(source_pen)]=result
        if records:
            cleaned[str(p)]=records
    return cleaned


def apply_palette_overrides(output, indices, mapping, pen_overrides):
    """Aplica Bayer manual apenas aos pixels dos pens indicados.

    O resultado usa o mesmo Bayer 4x4, em coordenadas do tile, que a ROM.
    Os outros pixels mantem exatamente o algoritmo escolhido.
    """
    import numpy as np
    out=np.asarray(output,dtype=np.uint8).copy()
    pix=np.asarray(indices,dtype=np.uint8)
    mapping=np.asarray(mapping,dtype=np.uint8)
    if not pen_overrides:
        return out
    if out.shape!=pix.shape or pix.ndim!=2 or pix.shape[0]%4 or pix.shape[1]%4:
        raise ValueError('Dithering manual exige matriz 2D multipla de quatro')
    yy,xx=np.indices(pix.shape)
    thresholds=(dither_bg.BAYER4[yy%4,xx%4]+0.5)/16.0
    for src_pen, rule in pen_overrides.items():
        pen=int(src_pen)
        mask=(pix==pen)
        if not mask.any():
            continue
        primary=int(rule.get('primary',mapping[pen]))
        secondary=int(rule['secondary'])
        if not 1<=primary<=15 or not 1<=secondary<=15:
            raise ValueError('Indice de paleta Mega Drive invalido')
        fraction=float(rule['mix'])/100.0
        out[mask & (thresholds<fraction)]=secondary
        out[mask & (thresholds>=fraction)]=primary
    return out
