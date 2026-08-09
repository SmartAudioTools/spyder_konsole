# -*- coding: utf-8 -*-
"""Le VRAI moteur de Konsole dans un dock Spyder, via le binding shiboken de QTermWidget.

HISTORIQUE DE SON EMPLACEMENT. Ne du greffon Terminal, sorti dans un paquet a part
(`smartos_konsole`) le 31/07/2026 pour que les greffons Terminal et Claude n'aient pas a
dependre l'un de l'autre, puis RAPATRIE ici le 09/08/2026 (decision utilisateur : le nom
smartos_konsole etait mal choisi — le moteur tient a KDE, pas a SmartOS — et en monde pip
la dependance s'exprime proprement : spyder_claude declare spyder-konsole dans son
pyproject et importe `spyder_konsole.konsole_view`).

C'est la voie demandee : `libqtermwidget6` est le moteur terminal de Konsole extrait en
widget Qt autonome (celui de QTerminal/LXQt). Le binding est genere par shiboken a
partir des en-tetes C++ (cf. qtermwidget_binding/ de ce depot), donc ce qui s'affiche ici
n'est pas une reimplementation : c'est le code de Konsole, avec son rendu, son
historique, sa selection et ses jeux de couleurs.

TROIS CHOIX D'INTEGRATION, demandes par l'utilisateur le 26/07/2026 :

  1. LE PROFIL KONSOLE FAIT FOI pour le comportement du shell. On lit le profil par
     defaut declare dans ~/.config/konsolerc (`DefaultProfile`), puis le fichier
     ~/.local/share/konsole/<profil> : shell a lancer, taille d'historique, variables
     d'environnement, police et jeu de couleurs s'ils y figurent. QTermWidget ne sait
     PAS lire ces profils tout seul — c'est un programme distinct de Konsole, avec sa
     propre configuration. Sans cette lecture, le terminal du dock ignorerait les
     reglages faits une fois pour toutes dans Konsole (ici : zsh, historique illimite).

  2. MAIS LE FOND EST CELUI DE SPYDER, pas celui de Konsole. Un panneau doit se fondre
     dans l'IDE : un rectangle noir au milieu d'une interface #19232D se voit comme un
     trou. On fabrique donc, a la volee, un jeu de couleurs derive de celui de Konsole
     dont on ne remplace QUE le fond et le texte par ceux de Spyder — les seize couleurs
     ANSI, elles, restent celles auxquelles l'utilisateur est habitue.

  3. LES RACCOURCIS. QTermWidget n'en fournit AUCUN de lui-meme — dans QTerminal ils
     viennent de l'application hote. On pose donc Ctrl+Maj+C / Ctrl+Maj+V (l'habitude
     Konsole) ET, a la demande de l'utilisateur, Ctrl+C / Ctrl+V simples.

     Ctrl+C simple demande une precaution, sans quoi le terminal devient inutilisable :
     dans un terminal, Ctrl+C n'est pas « copier », c'est INTERROMPRE le programme en
     cours. La regle retenue est celle de Windows Terminal et de VS Code :

         Ctrl+C  ->  copie S'IL Y A UNE SELECTION, sinon envoie l'interruption (0x03)

     L'octet 0x03 ecrit dans le pty declenche SIGINT par la discipline de ligne, comme
     une vraie frappe : on ne perd donc rien. Ctrl+V colle toujours ; ce qu'il coute est
     l'insertion litterale (`quoted-insert`) du shell, geste rare, qui reste accessible
     par Ctrl+Q.

UN SEUL MOTEUR. Un emulateur VT en Python pur avait ete ecrit le meme jour, comme repli
pour les machines sans binding (RaspberryPi5 : pas de roue PySide6 aarch64). Il a ete
SUPPRIME le 26/07/2026 sur demande de l'utilisateur : sept cents lignes et une couche de
selection de moteur a maintenir, pour une plateforme que nous ne testons jamais. Sans
binding, le panneau affiche desormais un message qui dit quoi faire — cf.
spyder/main_widget.py, _afficher_absence_du_binding.
"""

import configparser
import os

from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QKeySequence, QShortcut
from qtpy.QtWidgets import QFrame, QVBoxLayout

#: Le module natif est produit par qtermwidget_binding/build.sh (racine de ce depot). Son absence n'est
#: pas une exception a l'import — le greffon doit pouvoir se charger pour AFFICHER qu'il
#: manque, sans quoi Spyder l'avalerait en silence et le panneau serait introuvable.
try:
    import qtermwidget as _qtw
    DISPONIBLE = True
except ImportError:  # pragma: no cover - depend de la machine
    _qtw = None
    DISPONIBLE = False


#: Ou Konsole range ses profils et ses jeux de couleurs.
DOSSIER_KONSOLE = os.path.expanduser("~/.local/share/konsole")
FICHIER_KONSOLERC = os.path.expanduser("~/.config/konsolerc")

#: Ou l'on ecrit le jeu de couleurs derive. Sous ~/.local/share pour ne rien mettre dans
#: le dossier de Konsole : ce fichier est a nous, il se regenere, et Konsole n'a pas a
#: le proposer dans ses menus. Nom neutre "smartpythoneditor" (08/08/2026, distribution
#: du fork) plutot que "smartos" : ce dossier apparait chez des utilisateurs qui n'ont
#: jamais entendu parler de SmartOS. Pas de migration : le contenu se regenere seul,
#: l'ancien dossier ~/.local/share/smartos/ devient simplement orphelin.
DOSSIER_SCHEMAS = os.path.expanduser("~/.local/share/smartpythoneditor/qtermwidget-schemes")

#: Jeux de couleurs de repli, si le profil n'en nomme aucun.
SCHEMAS_PREFERES = ("BreezeModified", "Breeze", "Linux", "BlackOnWhite")


def _lire_ini(chemin):
    """Lit un fichier .profile/.colorscheme (format INI de KDE). {} si absent/illisible."""
    lecteur = configparser.ConfigParser(strict=False, interpolation=None)
    # KDE distingue la casse des cles ; configparser les abaisse par defaut.
    lecteur.optionxform = str
    try:
        lecteur.read(chemin, encoding="utf-8")
    except (OSError, configparser.Error):
        return {}
    return {section: dict(lecteur[section]) for section in lecteur.sections()}


def profil_konsole():
    """Retourne les reglages du profil Konsole par defaut, sous forme de dictionnaire.

    Cles produites (toutes optionnelles) : commande, historique (nombre de lignes, ou
    -1 pour illimite, ou 0 pour aucun), environnement (liste "CLE=valeur"), police,
    taille_police, schema.
    """
    reglages = {}

    konsolerc = _lire_ini(FICHIER_KONSOLERC)
    nom_profil = (konsolerc.get("Desktop Entry", {}).get("DefaultProfile")
                  or konsolerc.get("General", {}).get("DefaultProfile"))
    if not nom_profil:
        # Konsole ecrit DefaultProfile dans une section dont le nom a change au fil des
        # versions : plutot que de parier, on cherche la cle partout.
        for section in konsolerc.values():
            if "DefaultProfile" in section:
                nom_profil = section["DefaultProfile"]
                break
    if not nom_profil:
        return reglages

    profil = _lire_ini(os.path.join(DOSSIER_KONSOLE, nom_profil))
    if not profil:
        return reglages
    reglages["profil"] = nom_profil

    general = profil.get("General", {})
    if general.get("Command"):
        reglages["commande"] = general["Command"].split()
    if general.get("Environment"):
        # Konsole separe les variables par des virgules.
        reglages["environnement"] = [v for v in general["Environment"].split(",") if v]

    defilement = profil.get("Scrolling", {})
    mode = defilement.get("HistoryMode")
    if mode == "0":
        reglages["historique"] = 0        # aucun historique
    elif mode == "2":
        reglages["historique"] = -1       # illimite
    elif defilement.get("HistorySize"):
        try:
            reglages["historique"] = int(defilement["HistorySize"])
        except ValueError:
            pass

    apparence = profil.get("Appearance", {})
    if apparence.get("ColorScheme"):
        reglages["schema"] = apparence["ColorScheme"]
    if apparence.get("Font"):
        # Format Konsole : "Famille,taille,-1,5,50,0,0,0,0,0"
        morceaux = apparence["Font"].split(",")
        reglages["police"] = morceaux[0]
        if len(morceaux) > 1:
            try:
                reglages["taille_police"] = int(float(morceaux[1]))
            except ValueError:
                pass

    return reglages


def _composantes(valeur):
    """« #19232D » ou « 25,35,45 » -> « 25,35,45 » (le format des .colorscheme)."""
    texte = str(valeur).strip()
    if texte.startswith("#") and len(texte) == 7:
        return "%d,%d,%d" % (int(texte[1:3], 16), int(texte[3:5], 16), int(texte[5:7], 16))
    return texte


#: Dossiers ou chercher un jeu de couleurs a deriver, dans l'ordre.
DOSSIERS_SCHEMAS_SYSTEME = ("/usr/share/qtermwidget6/color-schemes",
                            "/usr/share/qtermwidget/color-schemes",
                            DOSSIER_KONSOLE)

#: Pose une seule fois par processus : le gestionnaire de jeux de couleurs de
#: qtermwidget met sa liste EN CACHE des la premiere lecture. Declarer le dossier apres
#: coup ne sert donc a rien — mesure le 26/07/2026 : le meme appel donne « absent »
#: apres un availableColorSchemes(), « present » avant.
_dossier_declare = False


def _fichier_schema(nom):
    for dossier in DOSSIERS_SCHEMAS_SYSTEME + (DOSSIER_SCHEMAS,):
        candidat = os.path.join(dossier, nom + ".colorscheme")
        if os.path.isfile(candidat):
            return candidat
    return None


def preparer_schema(profil, fond, texte, fond_intense=None, nom_derive="SpyderFond"):
    """Fabrique le jeu de couleurs de l'IDE et le rend visible. Retourne son nom.

    A appeler AVANT de creer le premier QTermWidget : c'est la seule fenetre ou la
    declaration du dossier est prise en compte (cf. `_dossier_declare`). On choisit la
    base en regardant les FICHIERS sur le disque plutot qu'en interrogeant
    availableColorSchemes(), justement pour ne pas figer le cache trop tot.

    `nom_derive` permet de fabriquer PLUSIEURS jeux dans la meme session — c'est ce dont
    se sert le greffon Claude, qui en prepare un par etat d'instance (fond rouge sombre
    « on t'attend », vert sombre « c'est fini »). Tous doivent etre ecrits avant la
    premiere lecture de la liste par qtermwidget, qui la met en cache definitivement.
    """
    global _dossier_declare

    base = None
    for candidat in ((profil.get("schema"),) if profil.get("schema") else ()) + SCHEMAS_PREFERES:
        if candidat and _fichier_schema(candidat):
            base = candidat
            break
    if base is None:
        return None

    nom = base
    if fond:
        derive = schema_aux_couleurs_de_spyder(base, fond, texte or "#DFE1E2",
                                               fond_intense, nom_derive)
        if derive:
            nom = derive
            if not _dossier_declare and _qtw is not None:
                _qtw.QTermWidget.addCustomColorSchemeDir(DOSSIER_SCHEMAS)
                _dossier_declare = True
    return nom


def schema_aux_couleurs_de_spyder(base, fond, texte, fond_intense=None,
                                  nom="SpyderFond"):
    """Derive un jeu de couleurs du jeu `base` en imposant le fond et le texte de Spyder.

    Retourne le nom du jeu ecrit, ou None si la base est introuvable. On ne touche PAS
    aux seize couleurs ANSI : ce sont elles qui donnent son allure a la sortie colorisee
    (invite, `ls`, diagnostics), et les remplacer par une palette Spyder rendrait
    illisible ce que l'utilisateur reconnait au premier coup d'oeil.
    """
    source = _fichier_schema(base)
    if source is None:
        return None

    contenu = _lire_ini(source)
    if not contenu:
        return None

    contenu.setdefault("Background", {})["Color"] = _composantes(fond)
    contenu.setdefault("BackgroundFaint", {})["Color"] = _composantes(fond)
    contenu.setdefault("BackgroundIntense", {})["Color"] = _composantes(
        fond_intense or fond)
    contenu.setdefault("Foreground", {})["Color"] = _composantes(texte)
    contenu.setdefault("ForegroundFaint", {})["Color"] = _composantes(texte)
    contenu.setdefault("ForegroundIntense", {})["Color"] = _composantes(texte)
    contenu.setdefault("General", {})["Description"] = "Spyder (fond de l'IDE)"
    contenu["General"]["Opacity"] = contenu.get("General", {}).get("Opacity", "1")

    ecrivain = configparser.ConfigParser(strict=False, interpolation=None)
    ecrivain.optionxform = str
    for section, valeurs in contenu.items():
        ecrivain[section] = valeurs

    os.makedirs(DOSSIER_SCHEMAS, exist_ok=True)
    with open(os.path.join(DOSSIER_SCHEMAS, nom + ".colorscheme"), "w",
              encoding="utf-8") as fichier:
        ecrivain.write(fichier, space_around_delimiters=False)
    return nom


class VueKonsole(QFrame):
    """Une session de terminal servie par le moteur de Konsole.

    QFrame et non QWidget : le cadre du panneau — gris au repos, bleu au focus — est
    pose par une feuille de style, et un QWidget nu ne dessine pas les bordures d'une
    feuille de style. C'est aussi la que la console IPython porte le sien (le cadre de
    son QTextEdit), ce qui aligne les deux panneaux.
    """

    sig_titre = Signal(str)
    sig_termine = Signal(int)

    #: Retrait du contenu par rapport au cadre, en pixels : un pour le trait, trois pour
    #: laisser voir l'arrondi des coins (SIZE_BORDER_RADIUS vaut 4 dans le theme).
    MARGE_CADRE = 3

    def __init__(self, parent=None, police=None, taille_police=10,
                 couleur_fond=None, couleur_texte=None, couleur_fond_intense=None):
        super().__init__(parent)
        self.setObjectName("terminal_smartos")   # cible de la feuille de style du cadre
        self.setFrameShape(QFrame.NoFrame)       # le cadre vient de la feuille, pas de Qt
        if not DISPONIBLE:
            raise RuntimeError(
                "Le binding qtermwidget n'est pas installe : lancer "
                "qtermwidget_binding/build.sh du depot spyder_konsole")

        self._profil = profil_konsole()
        # AVANT toute creation de widget : le jeu de couleurs derive doit exister et son
        # dossier etre declare, sinon qtermwidget ne le verra jamais (cache).
        self._schema = preparer_schema(self._profil, couleur_fond, couleur_texte,
                                       couleur_fond_intense)

        # startnow=0 : on veut regler le shell, le dossier et l'environnement AVANT que
        # le processus ne demarre. Avec startnow=1 le shell part dans le mauvais dossier,
        # et le corriger apres coup laisse une premiere invite fausse a l'ecran.
        self._terminal = _qtw.QTermWidget(0, self)

        self._appliquer_apparence(police, taille_police)

        layout = QVBoxLayout(self)
        # Marge = epaisseur du cadre + rayon des coins. Sans elle, le terminal est OPAQUE
        # et peint PAR-DESSUS le cadre : c'est ce qui mangeait le coin bas-gauche, defaut
        # signale par l'utilisateur le 26/07/2026. Meme piege que l'ecran de jeu du
        # greffon Pyxel, et meme remede.
        layout.setContentsMargins(self.MARGE_CADRE, self.MARGE_CADRE,
                                  self.MARGE_CADRE, self.MARGE_CADRE)
        layout.addWidget(self._terminal)

        self._terminal.finished.connect(self._sur_fin)
        self._terminal.titleChanged.connect(self._sur_titre)
        self._poser_raccourcis()

    # ------------------------------------------------------------- apparence

    def _appliquer_apparence(self, police, taille_police):
        from qtpy.QtGui import QFont, QFontDatabase

        famille = police or self._profil.get("police")
        taille = taille_police or self._profil.get("taille_police") or 10
        if famille:
            fonte = QFont(famille, taille)
        else:
            fonte = QFontDatabase.systemFont(QFontDatabase.FixedFont)
            fonte.setPointSize(taille)
        fonte.setStyleHint(QFont.Monospace)
        fonte.setFixedPitch(True)
        self._terminal.setTerminalFont(fonte)

        if self._schema:
            self._terminal.setColorScheme(self._schema)

        # Historique : le profil Konsole fait foi (ici HistoryMode=2, illimite).
        historique = self._profil.get("historique", 5000)
        self._terminal.setHistorySize(historique)
        # Sans barre de defilement, l'historique existe mais reste inaccessible a la
        # souris : le defaut de QTermWidget est NoScrollBar, il faut le dire.
        self._terminal.setScrollBarPosition(
            _qtw.QTermWidgetInterface.ScrollBarRight)
        self._terminal.setFlowControlEnabled(False)

    def appliquer_schema(self, nom=None):
        """Change le jeu de couleurs de CETTE session, a chaud. Sans nom : celui d'origine.

        C'est ainsi que le greffon Claude reproduit le fond rouge/vert que
        `claude-window.sh` pose sur une vraie fenetre Konsole par sequence OSC. La
        sequence, elle, n'est PAS envoyee a un panneau : le jeu de couleurs de
        qtermwidget est le chemin sur : il est relu par le moteur meme si le programme en
        cours redessine tout l'ecran, alors qu'une sequence OSC ecrite en concurrence
        d'un plein ecran se fait avaler (c'est pourquoi le hook l'ecrit trois fois).
        """
        nom = nom or self._schema
        if not nom:
            return False
        try:
            self._terminal.setColorScheme(nom)
        except Exception:      # jeu inconnu : on garde celui en place, sans casser
            return False
        return True

    #: Code de l'interruption (Ctrl+C) tel qu'il circule sur le pty.
    INTERRUPTION = "\x03"

    def _poser_raccourcis(self):
        """Les quatre raccourcis de copier/coller du terminal.

        Le contexte est `WidgetWithChildrenShortcut` pour qu'ils n'agissent que lorsque
        le terminal a le focus — sinon ils captureraient le copier de l'editeur.
        """
        for sequence, action in (("Ctrl+Shift+C", self.copier),
                                 ("Ctrl+Shift+V", self.coller),
                                 ("Ctrl+C", self.copier_ou_interrompre),
                                 ("Ctrl+V", self.coller)):
            raccourci = QShortcut(QKeySequence(sequence), self)
            raccourci.setContext(Qt.WidgetWithChildrenShortcut)
            raccourci.activated.connect(action)

    def copier_ou_interrompre(self):
        """Ctrl+C : copie s'il y a une selection, INTERROMPT sinon.

        C'est la seule facon d'avoir Ctrl+C en copier sans perdre l'interruption, dont
        on ne peut pas se passer dans un terminal (arreter une commande partie trop
        loin, sortir d'une invite bloquee). Comme un vrai terminal, on efface la
        selection apres la copie : sinon le Ctrl+C suivant copierait encore au lieu
        d'interrompre, et l'utilisateur croirait l'interruption cassee.
        """
        if self._selection_non_vide():
            self.copier()
            self._effacer_selection()
        else:
            self.envoyer(self.INTERRUPTION)

    def _selection_non_vide(self):
        try:
            return bool(self._terminal.selectedText(False).strip())
        except Exception:
            return False

    def _effacer_selection(self):
        """Vide la selection. La borne de fin est -1, et ce n'est pas un detail.

        Mesure du 26/07/2026 : `setSelectionEnd(0, 0)` laisse UN caractere selectionne
        (selectedText renvoie « L »), donc le Ctrl+C suivant copiait au lieu
        d'interrompre — le defaut se voyait au deuxieme appui, pas au premier.
        Avec une colonne de fin a -1, la selection est reellement vide.
        """
        try:
            self._terminal.setSelectionStart(0, 0)
            self._terminal.setSelectionEnd(0, -1)
        except Exception:
            pass

    # -------------------------------------------------------------- sessions

    def demarrer(self, commande=None, repertoire=None, environnement=None):
        commande = list(commande) if commande else (
            self._profil.get("commande") or [os.environ.get("SHELL", "/bin/bash")])
        self._terminal.setShellProgram(commande[0])
        self._terminal.setArgs(commande[1:])

        if repertoire and os.path.isdir(repertoire):
            self._terminal.setWorkingDirectory(repertoire)

        variables = dict(os.environ)
        for entree in self._profil.get("environnement", []):
            cle, _, valeur = entree.partition("=")
            if cle:
                variables[cle] = valeur
        if environnement:
            variables.update(environnement)
        variables["TERM"] = "xterm-256color"
        # Marqueur d'introspection : les scripts SmartOS qui pilotent KWin et D-Bus
        # doivent pouvoir distinguer ce terminal d'une vraie fenetre Konsole — il n'a ni
        # fenetre top-level a lui, ni service D-Bus.
        variables["SPYDER_NATIVE_TERMINAL"] = "1"
        for cle in ("KONSOLE_DBUS_SERVICE", "KONSOLE_DBUS_SESSION"):
            variables.pop(cle, None)
        self._terminal.setEnvironment(
            ["%s=%s" % (cle, valeur) for cle, valeur in variables.items()])

        self._terminal.startShellProgram()
        self._terminal.setFocus()

    def arreter(self, force=False):
        """Termine le shell de CETTE session, par son pid — jamais par nom."""
        pid = 0
        try:
            pid = self._terminal.getShellPID()
        except Exception:      # le shell peut deja etre sorti
            pid = 0
        if pid > 0:
            import signal
            try:
                os.kill(pid, signal.SIGKILL if force else signal.SIGHUP)
            except (ProcessLookupError, OSError):
                pass

    # --------------------------------------------------------------- edition

    def copier(self):
        self._terminal.copyClipboard()

    def coller(self, _texte=None):
        # QTermWidget colle lui-meme depuis le presse-papier, en respectant le mode
        # « collage entre crochets » du programme en cours : on ne passe pas le texte.
        self._terminal.pasteClipboard()

    def envoyer(self, texte):
        self._terminal.sendText(texte)

    # -------------------------------------------------------------- reactions

    def _sur_titre(self):
        titre = self._terminal.title()
        if titre:
            self.sig_titre.emit(titre)

    def _sur_fin(self):
        self.sig_termine.emit(0)

    def setFocus(self):  # noqa: N802 - on suit l'API Qt
        self._terminal.setFocus()
