# -*- coding: utf-8 -*-
"""Fonction de traduction du greffon.

`spyder.api.translations.get_translation("spyder_konsole")` marcherait aussi,
mais tant qu'aucun catalogue .mo n'est fourni elle affiche a chaque import
« Could not load translations for fr ... domain: 'spyder_konsole' » - du bruit
dans la console a chaque demarrage de Spyder (meme travers que spyder_line_profiler).

Les libelles sont ecrits directement en francais, la langue de cette installation.
On garde l'habillage `_(...)` pour pouvoir ajouter un catalogue plus tard sans
toucher au reste du code, sans en promettre un aujourd'hui.
"""


def _(message):
    return message
