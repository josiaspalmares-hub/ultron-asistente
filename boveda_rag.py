"""Motor de memoria de Ultron: búsqueda por relevancia (BM25) sobre los apuntes .md de 'boveda/wiki'.

Diseño para respuestas instantáneas sin saturar el contexto de la IA:
  · Índice invertido en memoria: una consulta solo toca los fragmentos que contienen sus palabras.
  · Indexación incremental: solo se vuelven a leer los archivos que cambiaron (firma = mtime + tamaño).
  · Caché en disco (boveda/.indice_rag.json): el arranque no re-lee toda la wiki.
  · Vigilante en segundo plano: la consulta nunca revisa el disco; el índice ya está al día.
  · Caché de consultas recientes (LRU) y salida acotada en caracteres.
"""
import math
import os
import json
import re
import threading
import time
from collections import Counter, OrderedDict
from pathlib import Path

from utilidades import norm, lanzar_supervisado

_STOP = set("de la el en y a los las un una que por con para del se su al es lo como mas pero sus le ya o este si porque esta "
            "entre cuando muy sin sobre tambien me hasta hay donde quien desde todo nos durante todos uno les ni contra otros "
            "ese eso ante ellos e esto antes algunos unos yo otro otras otra tanto esa estos mucho nada muchos cual poco ella "
            "estar estas algo mi mis tu te ti tus ellas que the and of to in is cual cuales hacer quiero dime sabes".split())
_RE_TOK = re.compile(r"[a-z0-9_+#.]{2,}")
_RE_LINK = re.compile(r"\[\[([^\]|#]+)")
_VERSION_CACHE = 2
_MAX_CHUNK = 700
_K1, _B = 1.5, 0.75


def _stem(w: str) -> str:
    """Singular aproximado (plurales en -s / -es) para que 'servomotores' encuentre 'servomotor'."""
    if len(w) > 5 and w.endswith("es"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s"):
        return w[:-1]
    return w


def tokens(texto):
    return [_stem(w) for w in _RE_TOK.findall(norm(texto)) if w not in _STOP]


def _parsear(ruta: Path):
    """Divide un .md en fragmentos por encabezado (máx. ~700 caracteres). Devuelve (titulo, fragmentos, enlaces)."""
    texto = ruta.read_text(encoding="utf-8", errors="ignore")
    titulo = next((l.lstrip("# ").strip() for l in texto.splitlines() if l.startswith("# ")), ruta.stem)
    enlaces = sorted(set(_RE_LINK.findall(texto)))
    fragmentos, seccion, buf = [], titulo, []

    def cerrar():
        cuerpo = "\n".join(buf).strip()
        if cuerpo:
            tf = Counter(tokens(cuerpo))
            fragmentos.append({"seccion": seccion, "texto": cuerpo, "tf": dict(tf), "ln": max(1, sum(tf.values())),
                               "tit": set(tokens(titulo)), "sec": set(tokens(seccion))})
        buf.clear()
    for linea in texto.splitlines():
        if linea.startswith("#"):
            cerrar()
            seccion = linea.lstrip("# ").strip() or seccion
        else:
            buf.append(linea)
            if sum(len(l) for l in buf) > _MAX_CHUNK:
                cerrar()
    cerrar()
    return titulo, fragmentos, enlaces


def _a_json(archivos):
    """Serializa el índice a JSON (tuplas -> listas, conjuntos -> listas ordenadas)."""
    return {rel: {**a, "sig": list(a["sig"]),
                  "fragmentos": [{**f, "tit": sorted(f["tit"]), "sec": sorted(f["sec"])} for f in a["fragmentos"]]}
            for rel, a in archivos.items()}


def _de_json(datos):
    return {rel: {**a, "sig": tuple(a["sig"]),
                  "fragmentos": [{**f, "tit": set(f["tit"]), "sec": set(f["sec"])} for f in a["fragmentos"]]}
            for rel, a in datos.items()}


class BovedaRAG:
    def __init__(self, carpeta="boveda/wiki", cache=None, log=print):
        self.carpeta = Path(carpeta)
        self.cache_path = Path(cache) if cache else self.carpeta.parent / ".indice_rag.json"
        self._log = log
        self._lock = threading.Lock()
        self._archivos = {}          # ruta relativa -> {"sig", "titulo", "fragmentos", "enlaces"}
        self._firma = None
        self._snap = None            # (fragmentos, postings, vocabulario, avgdl, enlaces): inmutable, se reemplaza entero
        self._consultas = OrderedDict()
        self._cargar_cache_disco()
        self.actualizar()

    # ── Indexación ──────────────────────────────────────────────────────────────────
    def _escanear(self):
        if not self.carpeta.exists():
            return {}
        out = {}
        for raiz, _, nombres in os.walk(self.carpeta):
            for n in nombres:
                if n.lower().endswith(".md"):
                    p = Path(raiz) / n
                    try:
                        st = p.stat()
                        out[str(p.relative_to(self.carpeta)).replace("\\", "/")] = (st.st_mtime_ns, st.st_size)
                    except OSError:
                        pass
        return out

    def _cargar_cache_disco(self):
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                datos = json.load(f)
            if datos.get("version") == _VERSION_CACHE:
                self._archivos = _de_json(datos["archivos"])
        except Exception:
            self._archivos = {}

    def _guardar_cache_disco(self):
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"version": _VERSION_CACHE, "archivos": _a_json(self._archivos)}, f, ensure_ascii=False)
            os.replace(tmp, self.cache_path)
        except Exception as e:
            self._log(f"[RAG] No se pudo guardar la caché del índice: {e}")

    def actualizar(self) -> bool:
        """Re-lee SOLO los archivos nuevos o modificados y reconstruye el índice. True si hubo cambios."""
        firma = self._escanear()
        with self._lock:
            if firma == self._firma and self._snap is not None:
                return False
            cambiado = False
            for rel in list(self._archivos):
                if rel not in firma:
                    del self._archivos[rel]
                    cambiado = True
            for rel, sig in firma.items():
                previo = self._archivos.get(rel)
                if previo and previo["sig"] == sig:
                    continue
                try:
                    titulo, frags, enlaces = _parsear(self.carpeta / rel)
                    self._archivos[rel] = {"sig": sig, "titulo": titulo, "fragmentos": frags, "enlaces": enlaces}
                    cambiado = True
                except Exception as e:
                    self._log(f"[RAG] No se pudo indexar {rel}: {e}")
            self._firma = firma
            self._snap = self._construir_snapshot()
            self._consultas.clear()
        if cambiado:
            self._guardar_cache_disco()
        return cambiado

    def _construir_snapshot(self):
        fragmentos, postings, enlaces = [], {}, {}
        for rel, a in sorted(self._archivos.items()):
            enlaces[Path(rel).stem] = a["enlaces"]
            for fr in a["fragmentos"]:
                idx = len(fragmentos)
                fragmentos.append(dict(fr, archivo=rel, titulo=a["titulo"]))
                for tok, tf in fr["tf"].items():
                    postings.setdefault(tok, []).append((idx, tf))
        avgdl = (sum(f["ln"] for f in fragmentos) / len(fragmentos)) if fragmentos else 1.0
        return fragmentos, postings, sorted(postings), avgdl, enlaces

    def iniciar_vigilante(self, intervalo=5.0):
        """Hilo de fondo que mantiene el índice al día; las consultas nunca esperan al disco."""
        def _bucle():
            while True:
                time.sleep(intervalo)
                self.actualizar()
        return lanzar_supervisado("rag-vigilante", _bucle, log=self._log)

    # ── Consulta ────────────────────────────────────────────────────────────────────
    def buscar(self, consulta, max_resultados=5):
        """Resultados ordenados por relevancia BM25 (con bonus por título/sección y por frase exacta)."""
        clave = (norm(consulta).strip(), int(max_resultados))
        with self._lock:
            snap = self._snap
            if clave in self._consultas:
                self._consultas.move_to_end(clave)
                return self._consultas[clave]
        if not snap or not snap[0]:
            return []
        fragmentos, postings, vocab, avgdl, enlaces = snap
        N = len(fragmentos)
        q = list(dict.fromkeys(tokens(consulta)))
        if not q:
            return []
        puntos = {}
        for w in q:
            usados = [(w, 1.0)] if w in postings else [(v, .6) for v in vocab if len(w) >= 4 and v.startswith(w[:5])][:5]
            for tok, peso in usados:
                lista = postings[tok]
                idf = math.log(1 + (N - len(lista) + .5) / (len(lista) + .5))
                for idx, tf in lista:
                    f = fragmentos[idx]
                    s = idf * tf * (_K1 + 1) / (tf + _K1 * (1 - _B + _B * f["ln"] / avgdl))
                    if tok in f["tit"]:
                        s += 1.5 * idf
                    if tok in f["sec"]:
                        s += 1.0 * idf
                    puntos[idx] = puntos.get(idx, 0.0) + s * peso
        res = []
        if puntos:
            candidatos = sorted(puntos.items(), key=lambda x: -x[1])[:max(30, max_resultados * 4)]
            frase = clave[0]
            if len(frase) > 6:                                  # bonus por frase exacta (solo en los candidatos)
                candidatos = [(i, s + (2.0 if frase in norm(fragmentos[i]["texto"]) else 0)) for i, s in candidatos]
                candidatos.sort(key=lambda x: -x[1])
            vistos = set()
            for idx, s in candidatos:
                f = fragmentos[idx]
                k = (f["archivo"], f["seccion"])
                if k in vistos:
                    continue
                vistos.add(k)
                res.append({"archivo": f["archivo"], "seccion": f["seccion"], "score": round(s, 2), "texto": f["texto"],
                            "enlaces": enlaces.get(Path(f["archivo"]).stem, []), "q": q})
                if len(res) >= max_resultados:
                    break
        with self._lock:
            self._consultas[clave] = res
            while len(self._consultas) > 64:
                self._consultas.popitem(last=False)
        return res

    @staticmethod
    def _recorte(texto, q, ancho=380):
        """Ventana de texto centrada en la primera palabra de la consulta que aparezca (norm conserva longitudes)."""
        n = norm(texto)
        pos = min((p for p in (n.find(w) for w in q) if p >= 0), default=0)
        ini = max(0, pos - ancho // 3)
        fin = min(len(texto), ini + ancho)
        return ("…" if ini else "") + texto[ini:fin].strip() + ("…" if fin < len(texto) else "")

    def buscar_texto(self, consulta, max_resultados=5, max_chars=2200):
        """Resultado listo para la IA: fragmentos breves y un tope de caracteres para no saturar el contexto."""
        try:
            if not self.carpeta.exists():
                return "La carpeta 'boveda/wiki' no existe todavía."
            max_resultados = max(1, min(int(max_resultados), 10))
            res = self.buscar(consulta, max_resultados)
            if not res:
                return f"No encontré nada sobre '{consulta}' en la bóveda."
            salida, usados, rel = [], 0, set()
            for r in res:
                bloque = f"[{r['archivo']} > {r['seccion']}] (relevancia {r['score']})\n{self._recorte(r['texto'], r['q'])}"
                if usados + len(bloque) > max_chars and salida:
                    break
                salida.append(bloque)
                usados += len(bloque)
                rel.update(r["enlaces"])
            extra = f"\nNotas relacionadas ([[enlaces]]): {', '.join(sorted(rel)[:8])}" if rel else ""
            return f"Resultados de la bóveda para '{consulta}':\n\n" + "\n\n".join(salida) + extra
        except Exception as e:
            return f"Error al buscar en la bóveda: {e}"

    def resumen_para_prompt(self, max_chars=1200):
        """Índice compacto (un título por nota) para el prompt del sistema: reemplaza volcar toda la wiki en el contexto."""
        with self._lock:
            archivos = sorted(self._archivos.items(), key=lambda kv: -kv[1]["sig"][0])
        if not archivos:
            return "Sin registros de memoria previos."
        lineas, usados = [], 0
        for i, (rel, a) in enumerate(archivos):
            linea = f"- {rel}: {a['titulo']}"
            if usados + len(linea) > max_chars:
                lineas.append(f"(+{len(archivos) - i} notas más; consúltalas con `buscar_en_boveda`)")
                break
            lineas.append(linea)
            usados += len(linea) + 1
        return "Notas disponibles (consulta su contenido con `buscar_en_boveda`):\n" + "\n".join(lineas)

    def estadisticas(self):
        with self._lock:
            snap = self._snap
        return {"notas": len(self._archivos), "fragmentos": len(snap[0]) if snap else 0, "terminos": len(snap[2]) if snap else 0}