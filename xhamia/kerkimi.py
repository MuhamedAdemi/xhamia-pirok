"""
Kërkim "i butë": çdo fjalë e kërkimit duhet të gjendet diku te fushat (pjesë e fjalës mjafton),
pa dallim shkronjash të mëdha/të vogla dhe pa dallim ë/e, ç/c.
P.sh. "nuri", "jusu", "flor", "jash flor" e gjejnë të gjithë shtëpinë "Jusuf Nuri Jashari" me
kontakt sporadik "Florijan Jashari".
"""

_PA_SHENJA = str.maketrans('ëËçÇ', 'eEcC')


def normalizo(teksti):
    return str(teksti or '').translate(_PA_SHENJA).lower()


def fjalet(kerkimi):
    return normalizo(kerkimi).split()


def perputhet(fjalet_e_kerkimit, *fushat):
    teksti = ' '.join(normalizo(f) for f in fushat)
    return all(f in teksti for f in fjalet_e_kerkimit)


def fushat_e_shtepise(sh):
    return (sh.nr_shtepise, sh.emri_kryefamiljarit, sh.emri_prindit, sh.mbiemri_kryefamiljarit,
            sh.kontakt_sporadik_emri, sh.nr_telefoni_kryesor, sh.nr_telefoni_sporadik,
            sh.kontakt_sporadik_telefoni, sh.email, sh.kontakt_sporadik_email)


def filtro(objektet, kerkimi, fushat_fn):
    fj = fjalet(kerkimi)
    if not fj:
        return list(objektet)
    return [o for o in objektet if perputhet(fj, *fushat_fn(o))]
