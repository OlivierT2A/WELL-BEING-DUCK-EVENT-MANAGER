import streamlit as st
import pandas as pd
import random
import base64
import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

# --- MOT DE PASSE ORGANISATEUR ---
MOT_DE_PASSE_ORGANISATEUR = "MARCPRESIDENT"

# --- 1. INITIALISATION DES VARIABLES DE SESSION ---
if 'categories_dict' not in st.session_state:
    st.session_state.categories_dict = {"Bien-être": 1.2, "Compétiteur": 1.05, "Très Bon": 1.0, "Joker": 1.0}
if 'nom_tournoi' not in st.session_state:
    st.session_state.nom_tournoi = "CBAB Duck's Manager Pro"
if 'joueurs' not in st.session_state:
    st.session_state.joueurs = []
if 'equipes' not in st.session_state:
    st.session_state.equipes = pd.DataFrame(columns=["ID", "Surnom", "J1", "Cat1", "J2", "Cat2", "Coeff"])
if 'matchs' not in st.session_state:
    st.session_state.matchs = pd.DataFrame(columns=["Ronde", "Terrain", "Equipe A", "Score A", "Equipe B", "Score B"])
if 'algo_classement' not in st.session_state:
    st.session_state.algo_classement = "Pondéré"
if 'bg_image_data' not in st.session_state:
    st.session_state.bg_image_data = None
if 'nb_terrains' not in st.session_state:
    st.session_state.nb_terrains = 7
if 'temp_joueurs' not in st.session_state:
    st.session_state.temp_joueurs = []
if 'erreur_saisie' not in st.session_state:
    st.session_state.erreur_saisie = None
if 'profil' not in st.session_state:
    st.session_state.profil = "Joueur"
if 'confirm_reset_matchs' not in st.session_state:
    st.session_state.confirm_reset_matchs = False
if 'confirm_reset_tournoi' not in st.session_state:
    st.session_state.confirm_reset_tournoi = False

# Configuration de la page
st.set_page_config(page_title=st.session_state.nom_tournoi, layout="wide")

# --- 2. FONCTIONS UTILITAIRES ---

def set_background(uploaded_file):
    """Applique une image de fond via CSS"""
    if uploaded_file is not None:
        bytes_data = uploaded_file.getvalue()
        b64_data = base64.b64encode(bytes_data).decode()
        st.markdown(f'''
            <style>
            .stApp {{
                background-image: url("data:image/jpeg;base64,{b64_data}");
                background-size: cover;
                background-attachment: fixed;
            }}
            </style>
            ''', unsafe_allow_html=True)
    else:
        st.markdown('''
            <style>
            .stApp {
                background-image: none;
                background-color: white;
            }
            </style>
            ''', unsafe_allow_html=True)

def get_current_round():
    """Calcule la ronde maximum actuelle"""
    if st.session_state.matchs.empty:
        return 0
    return int(st.session_state.matchs["Ronde"].max())

def joueur_existe(prenom, nom):
    """Vérifie si un joueur existe déjà"""
    return any(j['Prénom'].lower().strip() == prenom.lower().strip() and 
               j['Nom'].lower().strip() == nom.lower().strip() 
               for j in st.session_state.joueurs)

def joueur_dans_equipe(prenom, nom):
    """Vérifie si un joueur est déjà dans une équipe"""
    if st.session_state.equipes.empty:
        return False
    nom_complet = f"{prenom} {nom}"
    return nom_complet in st.session_state.equipes['J1'].values or nom_complet in st.session_state.equipes['J2'].values

def get_nom_complet(joueur):
    """Retourne le nom complet d'un joueur"""
    return f"{joueur['Prénom']} {joueur['Nom']}"

def est_organisateur():
    """Vérifie si l'utilisateur a le profil organisateur"""
    return st.session_state.profil == "Organisateur"

def est_joker(nom_joueur):
    """Vérifie si un joueur est un joker"""
    return "Joker" in nom_joueur

def trouver_equipe_avec_joker():
    """Trouve la première équipe contenant un joker"""
    if st.session_state.equipes.empty:
        return None
    for idx, eq in st.session_state.equipes.iterrows():
        if est_joker(eq['J1']) or est_joker(eq['J2']):
            return idx
    return None

def get_nom_affichage_equipe(equipe_row):
    """Retourne le nom d'affichage d'une équipe (surnom ou ID)"""
    if pd.notna(equipe_row['Surnom']) and equipe_row['Surnom'].strip():
        return equipe_row['Surnom']
    return equipe_row['ID']

# --- 3. LOGIQUE MÉTIER ---

def generer_paires_equilibrees(mode="nouveau"):
    """
    mode="nouveau" : régénère toutes les équipes
    mode="ajouter" : ajoute uniquement les joueurs non affectés (remplace joker en priorité)
    """
    if mode == "nouveau":
        joueurs_a_traiter = [j for j in st.session_state.joueurs 
                            if j['Prénom'].strip() != "" and j['Nom'].strip() != "" and j['Catégorie'] != "Joker"]
    else:
        joueurs_a_traiter = [j for j in st.session_state.joueurs 
                            if j['Prénom'].strip() != "" and j['Nom'].strip() != "" 
                            and j['Catégorie'] != "Joker"
                            and not joueur_dans_equipe(j['Prénom'], j['Nom'])]
    
    if len(joueurs_a_traiter) < 1 and mode == "ajouter":
        st.error("Aucun joueur non affecté disponible.")
        return
    
    if len(joueurs_a_traiter) < 2 and mode == "nouveau":
        st.error("Il faut au moins 2 joueurs valides.")
        return
    
    # MODE AJOUT : Remplacer les jokers en priorité
    if mode == "ajouter":
        idx_joker = trouver_equipe_avec_joker()
        
        # Tant qu'il y a des jokers et des joueurs disponibles
        while idx_joker is not None and len(joueurs_a_traiter) > 0:
            eq = st.session_state.equipes.loc[idx_joker]
            
            # Trouver le meilleur joueur pour remplacer le joker
            if est_joker(eq['J1']):
                # Le joker est J1, on cherche un joueur compatible avec J2
                partenaire_cat = eq['Cat2']
                joueurs_tries = sorted(joueurs_a_traiter, 
                                      key=lambda x: abs(st.session_state.categories_dict[x['Catégorie']] - 
                                                       st.session_state.categories_dict[partenaire_cat]))
                nouveau_joueur = joueurs_tries[0]
                st.session_state.equipes.at[idx_joker, 'J1'] = get_nom_complet(nouveau_joueur)
                st.session_state.equipes.at[idx_joker, 'Cat1'] = nouveau_joueur['Catégorie']
            else:
                # Le joker est J2
                partenaire_cat = eq['Cat1']
                joueurs_tries = sorted(joueurs_a_traiter, 
                                      key=lambda x: abs(st.session_state.categories_dict[x['Catégorie']] - 
                                                       st.session_state.categories_dict[partenaire_cat]))
                nouveau_joueur = joueurs_tries[0]
                st.session_state.equipes.at[idx_joker, 'J2'] = get_nom_complet(nouveau_joueur)
                st.session_state.equipes.at[idx_joker, 'Cat2'] = nouveau_joueur['Catégorie']
            
            # Recalculer le coefficient
            c1 = st.session_state.equipes.at[idx_joker, 'Cat1']
            c2 = st.session_state.equipes.at[idx_joker, 'Cat2']
            avg_coeff = (st.session_state.categories_dict[c1] + st.session_state.categories_dict[c2]) / 2
            st.session_state.equipes.at[idx_joker, 'Coeff'] = round(avg_coeff, 3)
            
            # Retirer le joueur de la liste
            joueurs_a_traiter = [j for j in joueurs_a_traiter 
                               if not (j['Prénom'] == nouveau_joueur['Prénom'] and j['Nom'] == nouveau_joueur['Nom'])]
            
            # Chercher le prochain joker
            idx_joker = trouver_equipe_avec_joker()
        
        # S'il reste des joueurs, créer de nouvelles équipes
        if len(joueurs_a_traiter) == 0:
            st.success("✅ Tous les jokers ont été remplacés !")
            return
    
    # Tri par coefficient pour équilibrer
    joueurs_tries = sorted(joueurs_a_traiter, 
                          key=lambda x: st.session_state.categories_dict[x['Catégorie']], 
                          reverse=True)
    
    # Gérer le joueur impair avec un joker
    joueur_avec_joker = None
    if len(joueurs_tries) % 2 == 1:
        joueur_avec_joker = joueurs_tries.pop()
    
    # Former les paires
    paires = []
    while len(joueurs_tries) >= 2:
        paires.append((joueurs_tries.pop(0), joueurs_tries.pop(-1)))
    
    # Calculer l'ID de départ
    if mode == "ajouter" and not st.session_state.equipes.empty:
        dernier_id = max([int(eq.replace("Équipe ", "")) for eq in st.session_state.equipes["ID"]])
        start_id = dernier_id + 1
    else:
        start_id = 1
        if mode == "nouveau":
            st.session_state.equipes = pd.DataFrame(columns=["ID", "Surnom", "J1", "Cat1", "J2", "Cat2", "Coeff"])
    
    new_teams = []
    for i, (p1, p2) in enumerate(paires, start_id):
        c1, c2 = p1['Catégorie'], p2['Catégorie']
        avg_coeff = (st.session_state.categories_dict[c1] + st.session_state.categories_dict[c2]) / 2
        equipe_id = f"Équipe {i}"
        new_teams.append({
            "ID": equipe_id,
            "Surnom": equipe_id,
            "J1": get_nom_complet(p1), 
            "Cat1": c1,
            "J2": get_nom_complet(p2), 
            "Cat2": c2, 
            "Coeff": round(avg_coeff, 3)
        })
    
    # Ajouter l'équipe avec joker si nécessaire
    if joueur_avec_joker:
        i = start_id + len(paires)
        equipe_id = f"Équipe {i}"
        c1 = joueur_avec_joker['Catégorie']
        avg_coeff = (st.session_state.categories_dict[c1] + 1.0) / 2
        new_teams.append({
            "ID": equipe_id,
            "Surnom": equipe_id,
            "J1": get_nom_complet(joueur_avec_joker),
            "Cat1": c1,
            "J2": f"Joker {i}",
            "Cat2": "Joker",
            "Coeff": round(avg_coeff, 3)
        })
        st.warning(f"⚠️ Joueur impair : {get_nom_complet(joueur_avec_joker)} joue avec un Joker (remplaçant à trouver)")
    
    if new_teams:
        if mode == "ajouter":
            st.session_state.equipes = pd.concat([st.session_state.equipes, pd.DataFrame(new_teams)], ignore_index=True)
            st.success(f"✅ {len(new_teams)} équipes ajoutées !")
        else:
            st.session_state.equipes = pd.DataFrame(new_teams)
            st.success(f"✅ {len(new_teams)} équipes créées !")

def generer_ronde_equitable():
    if st.session_state.equipes.empty:
        st.error("Veuillez d'abord générer les équipes.")
        return
    
    all_tids = st.session_state.equipes["ID"].tolist()
    stats_joues = {tid: 0 for tid in all_tids}
    historique = {tid: set() for tid in all_tids}
    
    if not st.session_state.matchs.empty:
        for _, row in st.session_state.matchs.iterrows():
            stats_joues[row["Equipe A"]] += 1
            stats_joues[row["Equipe B"]] += 1
            historique[row["Equipe A"]].add(row["Equipe B"])
            historique[row["Equipe B"]].add(row["Equipe A"])
    
    file_priorite = sorted(all_tids, key=lambda x: (stats_joues[x], random.random()))
    nouvelle_ronde_matchs = []
    deja_pris = set()
    prochaine_ronde = get_current_round() + 1
    
    # Première passe : matchs inédits uniquement
    for i, eq_a in enumerate(file_priorite):
        if eq_a in deja_pris: continue
        for j in range(i + 1, len(file_priorite)):
            eq_b = file_priorite[j]
            if eq_b in deja_pris: continue
            if eq_b not in historique[eq_a]:
                nouvelle_ronde_matchs.append({
                    "Ronde": prochaine_ronde, "Terrain": f"T{len(nouvelle_ronde_matchs)+1}",
                    "Equipe A": eq_a, "Score A": 0, "Equipe B": eq_b, "Score B": 0
                })
                deja_pris.add(eq_a); deja_pris.add(eq_b)
                break
        if len(nouvelle_ronde_matchs) >= st.session_state.nb_terrains: break
    
    # Si on n'a pas assez de matchs, autoriser les rediffusions
    if len(nouvelle_ronde_matchs) < st.session_state.nb_terrains and len(nouvelle_ronde_matchs) < len(all_tids) // 2:
        st.warning("⚠️ Toutes les combinaisons inédites sont épuisées. Création de matchs rediffusés...")
        
        for i, eq_a in enumerate(file_priorite):
            if eq_a in deja_pris: continue
            for j in range(i + 1, len(file_priorite)):
                eq_b = file_priorite[j]
                if eq_b in deja_pris: continue
                # Accepter même si déjà joué
                nouvelle_ronde_matchs.append({
                    "Ronde": prochaine_ronde, "Terrain": f"T{len(nouvelle_ronde_matchs)+1}",
                    "Equipe A": eq_a, "Score A": 0, "Equipe B": eq_b, "Score B": 0
                })
                deja_pris.add(eq_a); deja_pris.add(eq_b)
                break
            if len(nouvelle_ronde_matchs) >= st.session_state.nb_terrains: break

    if nouvelle_ronde_matchs:
        st.session_state.matchs = pd.concat([st.session_state.matchs, pd.DataFrame(nouvelle_ronde_matchs)], ignore_index=True)
        st.success(f"Ronde {prochaine_ronde} générée avec {len(nouvelle_ronde_matchs)} matchs !")
    else:
        st.warning("Impossible de créer de nouveaux matchs.")

def reinitialiser_matchs():
    """Réinitialise uniquement les matchs"""
    st.session_state.matchs = pd.DataFrame(columns=["Ronde", "Terrain", "Equipe A", "Score A", "Equipe B", "Score B"])
    st.session_state.confirm_reset_matchs = False
    st.success("✅ Matchs et classement réinitialisés !")

def reinitialiser_tournoi():
    """Réinitialise tout le tournoi"""
    keys_to_keep = ['profil']
    for key in list(st.session_state.keys()):
        if key not in keys_to_keep:
            del st.session_state[key]
    st.session_state.confirm_reset_tournoi = False

def generer_pdf_classement():
    """Génère un PDF du classement"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    
    # Titre
    titre = f"Classement - {st.session_state.nom_tournoi}"
    date_heure = datetime.now().strftime("%d/%m/%Y %H:%M")
    elements.append(Paragraph(titre, styles['Title']))
    elements.append(Paragraph(f"Date: {date_heure}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # Calculer classement
    if not st.session_state.matchs.empty:
        stats = []
        for _, eq in st.session_state.equipes.iterrows():
            eid = eq["ID"]
            m_eq = st.session_state.matchs[(st.session_state.matchs["Equipe A"] == eid) | (st.session_state.matchs["Equipe B"] == eid)]
            
            p_marques, p_encaisses, v, n, d = 0, 0, 0, 0, 0
            for _, m in m_eq.iterrows():
                if m["Score A"] == 0 and m["Score B"] == 0: continue
                is_a = (m["Equipe A"] == eid)
                ma, sa = (m["Score A"], m["Score B"]) if is_a else (m["Score B"], m["Score A"])
                p_marques += ma
                p_encaisses += sa
                if ma > sa: v += 1
                elif ma == sa: n += 1
                else: d += 1
            
            diff = p_marques - p_encaisses
            if st.session_state.algo_classement == "Pondéré":
                score = round(((v * 3) + (n * 1)) * eq["Coeff"], 2)
            else:
                score = (v * 2) + (n * 1)
            
            stats.append([
                get_nom_affichage_equipe(eq),
                f"{eq['J1']} & {eq['J2']}",
                v, n, d, diff, score
            ])
        
        stats.sort(key=lambda x: (x[6], x[5]), reverse=True)
        
        # Ajouter rang
        data = [["Rang", "Équipe", "Joueurs", "V", "N", "D", "Diff", "Points"]]
        for i, row in enumerate(stats, 1):
            data.append([i] + row)
        
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(table)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

def generer_csv_classement():
    """Génère un CSV du classement"""
    if st.session_state.matchs.empty:
        return None
    
    stats = []
    for _, eq in st.session_state.equipes.iterrows():
        eid = eq["ID"]
        m_eq = st.session_state.matchs[(st.session_state.matchs["Equipe A"] == eid) | (st.session_state.matchs["Equipe B"] == eid)]
        
        p_marques, p_encaisses, v, n, d = 0, 0, 0, 0, 0
        for _, m in m_eq.iterrows():
            if m["Score A"] == 0 and m["Score B"] == 0: continue
            is_a = (m["Equipe A"] == eid)
            ma, sa = (m["Score A"], m["Score B"]) if is_a else (m["Score B"], m["Score A"])
            p_marques += ma
            p_encaisses += sa
            if ma > sa: v += 1
            elif ma == sa: n += 1
            else: d += 1
        
        diff = p_marques - p_encaisses
        if st.session_state.algo_classement == "Pondéré":
            score = round(((v * 3) + (n * 1)) * eq["Coeff"], 2)
        else:
            score = (v * 2) + (n * 1)
        
        stats.append({
            "Équipe": get_nom_affichage_equipe(eq),
            "Joueurs": f"{eq['J1']} & {eq['J2']}",
            "V": v, "N": n, "D": d, "Diff": diff, "Points": score
        })
    
    df = pd.DataFrame(stats).sort_values(by=["Points", "Diff"], ascending=False)
    df.index = range(1, len(df) + 1)
    df.index.name = "Rang"
    
    # Ajouter métadonnées
    csv_buffer = io.StringIO()
    csv_buffer.write(f"# Tournoi: {st.session_state.nom_tournoi}\n")
    csv_buffer.write(f"# Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
    csv_buffer.write(f"# Méthode: {st.session_state.algo_classement}\n")
    csv_buffer.write("\n")
    
    df.to_csv(csv_buffer)
    return csv_buffer.getvalue().encode('utf-8')

# --- 4. INTERFACE UTILISATEUR ---

# Sidebar - Profil
with st.sidebar:
    st.header("👤 Profil Utilisateur")
    
    profil_actuel = st.radio("Choisir un profil:", ["Joueur", "Organisateur"], 
                             index=0 if st.session_state.profil == "Joueur" else 1,
                             key="radio_profil")
    
    if profil_actuel == "Organisateur" and st.session_state.profil == "Joueur":
        mdp = st.text_input("Mot de passe organisateur:", type="password", key="mdp_orga")
        if st.button("🔓 Valider"):
            if mdp.upper() == MOT_DE_PASSE_ORGANISATEUR:
                st.session_state.profil = "Organisateur"
                st.success("✅ Mode Organisateur activé !")
                st.rerun()
            else:
                st.error("❌ Mot de passe incorrect !")
    elif profil_actuel == "Joueur" and st.session_state.profil == "Organisateur":
        st.session_state.profil = "Joueur"
        st.info("Mode Joueur activé")
        st.rerun()
    
    st.divider()
    
    if st.session_state.profil == "Joueur":
        st.info("🎮 **Mode Joueur**\n\nVous pouvez :\n- Consulter tous les onglets\n- Proposer de nouveaux joueurs\n\nActions réservées à l'organisateur.")
    else:
        st.success("👑 **Mode Organisateur**\n\nAccès complet à toutes les fonctionnalités.")

if st.session_state.bg_image_data:
    set_background(st.session_state.bg_image_data)
else:
    set_background(None)

st.title(f"🏸 {st.session_state.nom_tournoi}")

# Créer les onglets
if est_organisateur():
    tabs = st.tabs(["👥 Joueurs", "🤝 Équipes", "🏸 Matchs & Scores", "🏆 Classement", "⚙️ Paramètres"])
else:
    tabs = st.tabs(["👥 Joueurs", "🤝 Équipes", "🏸 Matchs & Scores", "🏆 Classement"])

# -- JOUEURS --
with tabs[0]:
    st.subheader("Saisie des joueurs")
    
    if st.session_state.erreur_saisie:
        st.error(st.session_state.erreur_saisie)
    
    col1, col2, col3, col4 = st.columns([2, 2, 3, 1])
    with col1:
        new_prenom = st.text_input("Prénom", key="input_prenom")
    with col2:
        new_nom = st.text_input("Nom", key="input_nom")
    with col3:
        # Exclure "Joker" des catégories sélectionnables
        cats_disponibles = [c for c in st.session_state.categories_dict.keys() if c != "Joker"]
        new_cat = st.selectbox("Catégorie", options=cats_disponibles, key="input_cat")
    with col4:
        st.write("")
        st.write("")
        if st.button("➕ Ajouter"):
            prenom_clean = new_prenom.strip()
            nom_clean = new_nom.strip()
            
            if not prenom_clean or not nom_clean:
                st.session_state.erreur_saisie = "⚠️ Le prénom ET le nom doivent être renseignés !"
                st.rerun()
            elif joueur_existe(prenom_clean, nom_clean):
                st.session_state.erreur_saisie = f"⚠️ Le joueur {prenom_clean} {nom_clean} existe déjà dans la liste !"
                st.rerun()
            else:
                doublon_temp = any(j['Prénom'].lower().strip() == prenom_clean.lower() and 
                                  j['Nom'].lower().strip() == nom_clean.lower() 
                                  for j in st.session_state.temp_joueurs)
                if doublon_temp:
                    st.session_state.erreur_saisie = f"⚠️ Le joueur {prenom_clean} {nom_clean} est déjà en attente de validation !"
                    st.rerun()
                else:
                    st.session_state.temp_joueurs.append({
                        "Prénom": prenom_clean, 
                        "Nom": nom_clean, 
                        "Catégorie": new_cat
                    })
                    st.session_state.erreur_saisie = None
                    st.rerun()
    
    # Joueurs temporaires
    if st.session_state.temp_joueurs:
        st.subheader("Joueurs à valider")
        if not est_organisateur():
            st.info("👑 La validation des joueurs est réservée à l'organisateur.")
        
        # Boutons d'action groupée (organisateur uniquement)
        if est_organisateur():
            col_grp1, col_grp2 = st.columns(2)
            with col_grp1:
                if st.button("✅ Valider TOUS les joueurs", use_container_width=True):
                    for joueur in st.session_state.temp_joueurs:
                        if not joueur_existe(joueur["Prénom"], joueur["Nom"]):
                            st.session_state.joueurs.append(joueur)
                    st.session_state.temp_joueurs = []
                    st.session_state.erreur_saisie = None
                    st.success("✅ Tous les joueurs ont été validés !")
                    st.rerun()
            with col_grp2:
                if st.button("🗑️ Supprimer TOUS les joueurs", use_container_width=True):
                    st.session_state.temp_joueurs = []
                    st.session_state.erreur_saisie = None
                    st.success("✅ Tous les joueurs en attente ont été supprimés !")
                    st.rerun()
        
        st.divider()
        
        for idx, joueur in enumerate(st.session_state.temp_joueurs):
            col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 3, 2])
            with col1:
                st.write(f"**{len(st.session_state.joueurs) + idx + 1}**")
            with col2:
                st.write(joueur["Prénom"])
            with col3:
                st.write(joueur["Nom"])
            with col4:
                st.write(joueur["Catégorie"])
            with col5:
                col_valid, col_suppr = st.columns(2)
                with col_valid:
                    if st.button("✅", key=f"valid_{idx}", disabled=not est_organisateur()):
                        if not joueur["Prénom"].strip() or not joueur["Nom"].strip():
                            st.session_state.erreur_saisie = "Le prénom et le nom ne peuvent pas être vides."
                            st.rerun()
                        elif joueur_existe(joueur["Prénom"], joueur["Nom"]):
                            st.session_state.erreur_saisie = f"Le joueur {joueur['Prénom']} {joueur['Nom']} existe déjà !"
                            st.rerun()
                        else:
                            st.session_state.joueurs.append(joueur)
                            st.session_state.temp_joueurs.pop(idx)
                            st.session_state.erreur_saisie = None
                            st.rerun()
                with col_suppr:
                    if st.button("🗑️", key=f"del_temp_{idx}", disabled=not est_organisateur()):
                        st.session_state.temp_joueurs.pop(idx)
                        st.session_state.erreur_saisie = None
                        st.rerun()
        
        st.divider()

    # Liste des joueurs validés
    st.subheader("Liste des inscrits")
    if st.session_state.joueurs:
        for idx, joueur in enumerate(st.session_state.joueurs, 1):
            col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 3, 1])
            with col1:
                st.write(f"**{idx}**")
            with col2:
                st.write(joueur["Prénom"])
            with col3:
                st.write(joueur["Nom"])
            with col4:
                st.write(joueur["Catégorie"])
            with col5:
                if st.button("🗑️", key=f"del_joueur_{idx}", disabled=not est_organisateur()):
                    st.session_state.joueurs.pop(idx - 1)
                    st.rerun()
    else:
        st.info("Aucun joueur inscrit pour le moment.")
    
    st.divider()
    
    # Import/Export Joueurs
    if est_organisateur():
        col_io1, col_io2 = st.columns(2)
        
        with col_io1:
            st.subheader("📥 Importer des joueurs")
            uploaded_joueurs = st.file_uploader("Fichier CSV (Prénom,Nom,Catégorie)", type=['csv'], key="import_joueurs")
            if uploaded_joueurs and st.button("Charger le fichier", key="btn_import_joueurs"):
                try:
                    df_import = pd.read_csv(uploaded_joueurs)
                    if all(col in df_import.columns for col in ['Prénom', 'Nom', 'Catégorie']):
                        count = 0
                        for _, row in df_import.iterrows():
                            if not joueur_existe(row['Prénom'], row['Nom']) and row['Catégorie'] != "Joker":
                                st.session_state.joueurs.append({
                                    'Prénom': row['Prénom'],
                                    'Nom': row['Nom'],
                                    'Catégorie': row['Catégorie']
                                })
                                count += 1
                        st.success(f"✅ {count} joueurs importés !")
                    else:
                        st.error("Le CSV doit contenir: Prénom, Nom, Catégorie")
                except Exception as e:
                    st.error(f"Erreur d'import: {e}")
        
        with col_io2:
            st.subheader("📤 Exporter les joueurs")
            if st.session_state.joueurs:
                df_export = pd.DataFrame(st.session_state.joueurs)
                csv = df_export.to_csv(index=False).encode('utf-8')
                st.download_button("💾 Télécharger CSV", csv, "joueurs.csv", "text/csv")
    
    st.divider()
    
    # Boutons de génération
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔥 GÉNÉRER LES ÉQUIPES", use_container_width=True, disabled=not est_organisateur()):
            generer_paires_equilibrees(mode="nouveau")
            st.rerun()
    with col2:
        joueurs_non_affectes = [j for j in st.session_state.joueurs 
                                if not joueur_dans_equipe(j['Prénom'], j['Nom']) and j['Catégorie'] != "Joker"]
        if len(joueurs_non_affectes) >= 1:
            if st.button("➕ AJOUTER DES ÉQUIPES", use_container_width=True, disabled=not est_organisateur()):
                generer_paires_equilibrees(mode="ajouter")
                st.rerun()
        else:
            st.button("➕ AJOUTER DES ÉQUIPES", use_container_width=True, disabled=True, 
                     help="Il faut au moins 1 joueur non affecté")

# -- ÉQUIPES --
with tabs[1]:
    st.subheader("Paires constituées")
    if not st.session_state.equipes.empty:
        # Permettre l'édition des surnoms si organisateur
        if est_organisateur():
            st.session_state.equipes = st.data_editor(
                st.session_state.equipes,
                use_container_width=True,
                column_config={
                    "ID": st.column_config.TextColumn(disabled=True),
                    "Surnom": st.column_config.TextColumn("Surnom d'équipe", help="Modifiable"),
                    "J1": st.column_config.TextColumn(disabled=True),
                    "Cat1": st.column_config.TextColumn(disabled=True),
                    "J2": st.column_config.TextColumn(disabled=True),
                    "Cat2": st.column_config.TextColumn(disabled=True),
                    "Coeff": st.column_config.NumberColumn(disabled=True),
                },
                key="editeur_equipes",
                hide_index=True
            )
        else:
            st.dataframe(st.session_state.equipes, use_container_width=True, hide_index=True)
        
        # Import/Export Équipes
        if est_organisateur():
            st.divider()
            col_io1, col_io2 = st.columns(2)
            
            with col_io1:
                st.subheader("📥 Importer des équipes")
                uploaded_equipes = st.file_uploader("Fichier CSV", type=['csv'], key="import_equipes")
                if uploaded_equipes and st.button("Charger le fichier", key="btn_import_equipes"):
                    try:
                        df_import = pd.read_csv(uploaded_equipes)
                        required = ['ID', 'Surnom', 'J1', 'Cat1', 'J2', 'Cat2', 'Coeff']
                        if all(col in df_import.columns for col in required):
                            st.session_state.equipes = df_import
                            st.success("✅ Équipes importées !")
                        else:
                            st.error("Format CSV invalide")
                    except Exception as e:
                        st.error(f"Erreur: {e}")
            
            with col_io2:
                st.subheader("📤 Exporter les équipes")
                csv = st.session_state.equipes.to_csv(index=False).encode('utf-8')
                st.download_button("💾 Télécharger CSV", csv, "equipes.csv", "text/csv")
    else:
        st.info("Les équipes apparaîtront ici après génération.")

# -- MATCHS --
with tabs[2]:
    col_a, col_b = st.columns([1, 1])
    if col_a.button("🎲 Lancer une nouvelle ronde", disabled=not est_organisateur()):
        generer_ronde_equitable()
        st.rerun()
    
    st.write(f"**Ronde actuelle : {get_current_round()}**")
    
    if not st.session_state.matchs.empty:
        # Remplacer les IDs par les surnoms pour l'affichage
        matchs_display = st.session_state.matchs.copy()
        for idx, row in matchs_display.iterrows():
            eq_a = st.session_state.equipes[st.session_state.equipes['ID'] == row['Equipe A']]
            eq_b = st.session_state.equipes[st.session_state.equipes['ID'] == row['Equipe B']]
            if not eq_a.empty:
                matchs_display.at[idx, 'Equipe A'] = get_nom_affichage_equipe(eq_a.iloc[0])
            if not eq_b.empty:
                matchs_display.at[idx, 'Equipe B'] = get_nom_affichage_equipe(eq_b.iloc[0])
        
        if est_organisateur():
            matchs_edited = st.data_editor(
                matchs_display,
                use_container_width=True,
                column_config={
                    "Ronde": st.column_config.NumberColumn(disabled=True),
                    "Terrain": st.column_config.TextColumn(disabled=True),
                    "Equipe A": st.column_config.TextColumn(disabled=True),
                    "Equipe B": st.column_config.TextColumn(disabled=True),
                },
                key="editeur_matchs",
                hide_index=True
            )
            # Synchroniser les scores
            st.session_state.matchs['Score A'] = matchs_edited['Score A']
            st.session_state.matchs['Score B'] = matchs_edited['Score B']
        else:
            st.dataframe(matchs_display, use_container_width=True, hide_index=True)
        
        # Import/Export Matchs
        if est_organisateur():
            st.divider()
            col_io1, col_io2 = st.columns(2)
            
            with col_io1:
                st.subheader("📥 Importer des matchs")
                uploaded_matchs = st.file_uploader("Fichier CSV", type=['csv'], key="import_matchs")
                if uploaded_matchs and st.button("Charger le fichier", key="btn_import_matchs"):
                    try:
                        df_import = pd.read_csv(uploaded_matchs)
                        required_cols = ['Ronde', 'Terrain', 'Equipe A', 'Score A', 'Equipe B', 'Score B']
                        if all(col in df_import.columns for col in required_cols):
                            st.session_state.matchs = df_import
                            st.success("✅ Matchs importés !")
                        else:
                            st.error("Format CSV invalide")
                    except Exception as e:
                        st.error(f"Erreur: {e}")
            
            with col_io2:
                st.subheader("📤 Exporter les matchs")
                csv = st.session_state.matchs.to_csv(index=False).encode('utf-8')
                st.download_button("💾 Télécharger CSV", csv, "matchs.csv", "text/csv")

# -- CLASSEMENT --
with tabs[3]:
    st.header(f"Classement Général - Mode {st.session_state.algo_classement}")
    
    if not st.session_state.matchs.empty:
        stats = []
        for _, eq in st.session_state.equipes.iterrows():
            eid = eq["ID"]
            m_eq = st.session_state.matchs[(st.session_state.matchs["Equipe A"] == eid) | (st.session_state.matchs["Equipe B"] == eid)]
            
            p_marques, p_encaisses, v, n, d = 0, 0, 0, 0, 0
            for _, m in m_eq.iterrows():
                if m["Score A"] == 0 and m["Score B"] == 0: continue
                is_a = (m["Equipe A"] == eid)
                ma, sa = (m["Score A"], m["Score B"]) if is_a else (m["Score B"], m["Score A"])
                p_marques += ma
                p_encaisses += sa
                if ma > sa: v += 1
                elif ma == sa: n += 1
                else: d += 1
            
            diff = p_marques - p_encaisses
            if st.session_state.algo_classement == "Pondéré":
                score = round(((v * 3) + (n * 1)) * eq["Coeff"], 2)
            else:
                score = (v * 2) + (n * 1)
            
            stats.append({
                "Équipe": get_nom_affichage_equipe(eq),
                "Joueurs": f"{eq['J1']} & {eq['J2']}",
                "V": v, "N": n, "D": d, "Diff": diff, "Points": score
            })
        
        df_classement = pd.DataFrame(stats).sort_values(by=["Points", "Diff"], ascending=False)
        df_classement.index = range(1, len(df_classement) + 1)
        st.dataframe(df_classement, use_container_width=True)
        
        # Export classement
        st.divider()
        st.subheader("📤 Exporter le classement")
        col_exp1, col_exp2 = st.columns(2)
        
        with col_exp1:
            csv_data = generer_csv_classement()
            if csv_data:
                filename = f"classement_{st.session_state.nom_tournoi}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
                st.download_button(
                    "💾 Télécharger CSV",
                    csv_data,
                    filename,
                    "text/csv",
                    use_container_width=True
                )
        
        with col_exp2:
            pdf_data = generer_pdf_classement()
            filename = f"classement_{st.session_state.nom_tournoi}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
            st.download_button(
                "📄 Télécharger PDF",
                pdf_data,
                filename,
                "application/pdf",
                use_container_width=True
            )
    else:
        st.info("Aucun match joué pour le moment.")

# -- PARAMÈTRES --
if est_organisateur():
    with tabs[4]:
        st.subheader("⚙️ Configuration Générale")
        
        nouveau_nom = st.text_input("Nom du Tournoi", st.session_state.nom_tournoi)
        if nouveau_nom != st.session_state.nom_tournoi:
            st.session_state.nom_tournoi = nouveau_nom
            st.rerun()
        
        st.session_state.nb_terrains = st.number_input("Nombre de terrains", 1, 50, st.session_state.nb_terrains)
        st.session_state.algo_classement = st.radio("Méthode de classement", ["Pondéré", "Standard"])
        
        st.divider()
        st.subheader("🏷️ Catégories et Coefficients")
        
        for cat, coef in list(st.session_state.categories_dict.items()):
            if cat == "Joker":
                continue  # Ne pas afficher Joker dans la liste éditable
            c1, c2, c3 = st.columns([2, 2, 1])
            c1.write(f"**{cat}**")
            new_c = c2.number_input(f"Coeff", 0.5, 3.0, coef, 0.05, key=f"cfg_{cat}", label_visibility="collapsed")
            st.session_state.categories_dict[cat] = new_c
            if c3.button("Supprimer", key=f"del_{cat}"):
                del st.session_state.categories_dict[cat]
                st.rerun()
                
        with st.expander("➕ Ajouter une catégorie"):
            nc1, nc2 = st.columns(2)
            n_name = nc1.text_input("Nom (ex: Espoir)")
            n_coef = nc2.number_input("Coeff", 0.5, 3.0, 1.0, 0.05)
            if st.button("Enregistrer catégorie"):
                if n_name and n_name != "Joker":
                    st.session_state.categories_dict[n_name] = n_coef
                    st.rerun()

        st.divider()
        st.subheader("🖼️ Personnalisation visuelle")
        
        img_fond = st.file_uploader("Image de fond (JPG/PNG)", type=["jpg", "jpeg", "png"])
        if img_fond:
            st.session_state.bg_image_data = img_fond
            st.rerun()
        
        if st.session_state.bg_image_data is not None:
            if st.button("🗑️ Supprimer l'image de fond"):
                st.session_state.bg_image_data = None
                st.rerun()

        st.divider()
        st.subheader("🔄 Réinitialisation")
        
        # Bouton réinitialiser matchs
        if not st.session_state.confirm_reset_matchs:
            if st.button("🔄 Réinitialiser les Matchs & Classement", use_container_width=True):
                st.session_state.confirm_reset_matchs = True
                st.rerun()
        else:
            st.warning("⚠️ Êtes-vous sûr de vouloir réinitialiser tous les matchs et le classement ? Cette action est irréversible !")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ OUI, Réinitialiser", use_container_width=True, type="primary"):
                    reinitialiser_matchs()
                    st.rerun()
            with col2:
                if st.button("❌ Annuler", use_container_width=True):
                    st.session_state.confirm_reset_matchs = False
                    st.rerun()
        
        st.divider()
        
        # Bouton réinitialiser tournoi
        if not st.session_state.confirm_reset_tournoi:
            if st.button("⌛ RÉINITIALISER TOUT LE TOURNOI", use_container_width=True):
                st.session_state.confirm_reset_tournoi = True
                st.rerun()
        else:
            st.error("🚨 ATTENTION : Vous allez supprimer TOUTES les données du tournoi (joueurs, équipes, matchs) ! Cette action est IRRÉVERSIBLE !")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ OUI, Tout Supprimer", use_container_width=True, type="primary"):
                    reinitialiser_tournoi()
                    st.rerun()
            with col2:
                if st.button("❌ Annuler", use_container_width=True):
                    st.session_state.confirm_reset_tournoi = False
                    st.rerun()
