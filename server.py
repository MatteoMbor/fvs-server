# Il piccolo forno dei Variable Font.
from flask import Flask, request, Response
from flask_cors import CORS
import ufoLib2
from ufo2ft import compileTTF
from fontTools.cu2qu.ufo import fonts_to_quadratic
from fontTools.designspaceLib import (DesignSpaceDocument, AxisDescriptor,
                                      SourceDescriptor)
from fontTools import varLib
import io, os, tempfile

app = Flask(__name__)
CORS(app)
@app.route('/')
def salute():
    return 'FVS Font Server attivo ✓'

def add_contour(contour, pen, asc):
    # coordinate del sito con la y ribaltata (il font la vuole in su)
    for s in contour:
        c = s['cmd']
        if c == 'M':   pen.moveTo((s['x'], asc - s['y']))
        elif c == 'L': pen.lineTo((s['x'], asc - s['y']))
        elif c == 'C': pen.curveTo((s['c1x'], asc - s['c1y']),
                                   (s['c2x'], asc - s['c2y']),
                                   (s['x'],  asc - s['y']))
        elif c == 'Z': pen.closePath()


def build_master_ufo(data, master_key):
    ufo = ufoLib2.Font()
    ufo.info.familyName = data['familyName']
    ufo.info.styleName = master_key
    ufo.info.unitsPerEm = data['upm']
    ufo.info.ascender = data['asc']
    ufo.info.descender = data['desc']

    notdef = ufo.newGlyph('.notdef')
    notdef.width = data['advance']
    space = ufo.newGlyph('space')
    space.width = data['advance']

    for ch, masters in data['glyphs'].items():
        g = ufo.newGlyph('uni%04X' % ord(ch))
        g.width = data['advance']
        g.unicodes = [ord(ch)]
        pen = g.getPen()
        for contour in masters[master_key]:
            add_contour(contour, pen, data['asc'])
    return ufo


@app.route('/build', methods=['POST'])
def build():
    data = request.get_json()

    # accetta sia 'axes' (lista, formato nuovo) sia 'axis' (formato vecchio)
    axes = data.get('axes')
    if axes is None:
        axes = [data['axis']]

    # 1. i tre master
    ufos = [build_master_ufo(data, k) for k in ('min', 'def', 'max')]

    # 2. cubiche -> quadratiche INSIEME (punti identici tra master)
    fonts_to_quadratic(ufos, max_err=1.0)

    # 3. compila i master in TTF temporanei
    tmp = tempfile.mkdtemp()
    paths = []
    for key, ufo in zip(('min', 'def', 'max'), ufos):
        ttf = compileTTF(ufo, convertCubics=False)
        p = os.path.join(tmp, 'master_%s.ttf' % key)
        ttf.save(p)
        paths.append((key, p))

    # 4. designspace: assi + posizioni dei master
    ds = DesignSpaceDocument()
    for axis in axes:
        a = AxisDescriptor()
        a.tag, a.name = axis['tag'], axis['name']
        a.minimum, a.default, a.maximum = axis['min'], axis['def'], axis['max']
        ds.addAxis(a)

    for key, p in paths:
        s = SourceDescriptor()
        s.path = p
        loc = {}
        for axis in axes:
            if key == 'min':   loc[axis['name']] = axis['min']
            elif key == 'def': loc[axis['name']] = axis['def']
            else:              loc[axis['name']] = axis['max']
        s.location = loc
        if key == 'def':
            s.copyInfo = True
        ds.addSource(s)

    # 5. fontTools cuce fvar/gvar/HVAR
    vf, _, _ = varLib.build(ds)

    buf = io.BytesIO()
    vf.save(buf)
    return Response(buf.getvalue(), mimetype='font/ttf')


if __name__ == '__main__':
    import os
    porta = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=porta)
