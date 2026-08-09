// En-tete d'entree du generateur shiboken : tout ce qui est inclus ici est analyse par
// libclang, et ce qui est declare dans bindings.xml en est extrait pour devenir un
// module Python.
//
// QTermWidget est le moteur terminal de Konsole extrait en widget Qt autonome
// (bibliotheque libqtermwidget6, celle de QTerminal/LXQt). Le binder, c'est obtenir
// dans Spyder le VRAI terminal de KDE — rendu, historique, selection, jeux de couleurs
// — sans reimplementer d'emulateur et sans navigateur embarque.

#ifndef SPYDER_QTERMWIDGET_BINDINGS_H
#define SPYDER_QTERMWIDGET_BINDINGS_H

#define QT_ANNOTATE_ACCESS_SPECIFIER(a) __attribute__((annotate(#a)))

#include <qtermwidget.h>

#endif  // SPYDER_QTERMWIDGET_BINDINGS_H
