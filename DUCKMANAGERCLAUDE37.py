""" 
DUCK MANAGER PRO - VERSION AVANCÉE AVEC MODE INDIVIDUEL ÉQUILIBRÉ ET CLÔTURE
Copiez ce code dans un fichier app.py et lancez avec: streamlit run app.py 

NOUVEAUTÉS AJOUTÉES:
✅ Mode individuel avec priorité aux joueurs ayant le moins joué
✅ Bouton "Générer les derniers rounds" pour clôturer le tournoi
✅ Équilibrage automatique du nombre de matchs par joueur
✅ Utilisation de "jokers" pour compléter les équipes en fin de tournoi
✅ Exclusion des points des jokers du classement individuel
✅ Gestion intelligente des retards de matchs
✅ Deux modes distincts: Classique (équipes fixes) et Individuel (équipes variables)
✅ Interface optimisée avec Streamlit
"""

import streamlit as st
import pandas as pd
import random
import base64
import io
import json
from datetime import datetime
from collections import defaultdict, Counter
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

MOT_DE_PASSE_ORGANISATEUR = "MARCPRESIDENT"

# === INITIALISATION ===
defaults = {
    'categories_dict': {"Bien-être": 1.2, "Compétiteur": 1.05, "Très Bon": 1.0, "Joker": 1.0},
    'nom_tournoi': "CBAB Duck's Manager Pro",
    'joueurs': [],
    
    # Structure pour le mode classique
    'equipes_fixes': pd.DataFrame(columns=["ID", "Surnom", "J1", "Cat1", "J2", "Cat2", "Coeff"]),
    
    # Structure pour le mode individuel
    'historique_equipes': pd.DataFrame(columns=["Round", "ID", "Surnom", "J1", "Cat1", "J2", "Cat2", "Coeff"]),
    
    # Matchs détaillés avec informations sur les joueurs
    'matchs_detail': pd.DataFrame(columns=[
        "Round", "Terrain", "Type",
        "Equipe_A_ID", "J1_A", "J2_A", "Score_A",
        "Equipe_B_ID", "J1_B", "J2_B", "Score_B",
        "Jokers"
    ]),
    
    # Matchs simplifiés pour compatibilité
    'matchs': pd.DataFrame(columns=["Round", "Terrain", "Type", "Equipe A", "Score A", "Equipe B", "Score B"]),
    
    'algo_classement': "Pondéré",
    'algo_classement_individuel': "Pondéré",
    'mode_tournoi': "Classique",
    'bg_image_data': None,
    'nb_terrains': 7,
    'temp_joueurs': [],
    'erreur_saisie': None,
    'profil': "Joueur",
    'confirm_reset_matchs': False,
    'confirm_reset_tournoi': False,
    'confirm_import_matchs': False,
    'pending_matchs_import': None,
    
    # Nouveau: statistiques des joueurs pour équilibrage
    'statistiques_joueurs': {}
}

# === FONCTIONS DE BASE ===

def set_background(f):
    if f:
        st.markdown(f'<style>.stApp{{background-image:url("data:image/jpeg;base64,{base64.b64encode(f.getvalue()).decode()}");background-size:cover;background-attachment:fixed;}}</style>', unsafe_allow_html=True)
    else:
        st.markdown('<style>.stApp{background-image:none;background-color:white;}</style>', unsafe_allow_html=True)

def get_current_round():
    return 0 if st.session_state.matchs.empty else int(st.session_state.matchs["Round"].max())

def joueur_existe(p, n):
    return any(j['Prénom'].lower().strip()==p.lower().strip() and j['Nom'].lower().strip()==n.lower().strip() for j in st.session_state.joueurs)

def get_nom_complet(j):
    return f"{j['Prénom']} {j['Nom']}"

def est_organisateur():
    return st.session_state.profil == "Organisateur"

def get_nom_affichage_equipe(eq):
    return eq['Surnom'] if pd.notna(eq['Surnom']) and eq['Surnom'].strip() else eq['ID']

def get_categorie_joueur(nom_complet):
    if not isinstance(nom_complet, str):
        return "Joker"
    
    if "Joker" in nom_complet:
        return "Joker"
    
    for joueur in st.session_state.joueurs:
        if get_nom_complet(joueur) == nom_complet:
            return joueur['Catégorie']
    return "Joker"

def get_equipes_actuelles():
    if st.session_state.mode_tournoi == "Classique":
        return st.session_state.equipes_fixes
    else:
        if st.session_state.historique_equipes.empty:
            return pd.DataFrame()
        dernier_round = st.session_state.historique_equipes["Round"].max()
        return st.session_state.historique_equipes[
            st.session_state.historique_equipes["Round"] == dernier_round
        ].drop(columns=["Round"])

def get_equipes_par_round(round_num):
    if st.session_state.historique_equipes.empty:
        return pd.DataFrame()
    return st.session_state.historique_equipes[
        st.session_state.historique_equipes["Round"] == round_num
    ].drop(columns=["Round"])

# === NOUVELLES FONCTIONS POUR LE MODE INDIVIDUEL ÉQUILIBRÉ ===

def calculer_statistiques_joueurs():
    """Calcule le nombre de matchs joués par chaque joueur"""
    stats = defaultdict(int)
    
    if st.session_state.matchs_detail.empty:
        return stats
    
    for _, match in st.session_state.matchs_detail.iterrows():
        # Ignorer les matchs non joués
        if match["Score_A"] == 0 and match["Score_B"] == 0:
            continue
        
        # Compter pour l'équipe A
        for joueur in [match['J1_A'], match['J2_A']]:
            if joueur and "Joker" not in str(joueur):
                stats[joueur] += 1
        
        # Compter pour l'équipe B
        for joueur in [match['J1_B'], match['J2_B']]:
            if joueur and "Joker" not in str(joueur):
                stats[joueur] += 1
    
    return stats

def generer_equipes_equilibrees():
    """Génère des équipes équilibrées en priorisant les joueurs ayant le moins joué"""
    if len(st.session_state.joueurs) < 2:
        st.error("Il faut au moins 2 joueurs")
        return False
    
    # Calculer les statistiques actuelles
    stats = calculer_statistiques_joueurs()
    
    # Liste des joueurs avec leur nombre de matchs
    joueurs_avec_stats = []
    for joueur in st.session_state.joueurs:
        nom_complet = get_nom_complet(joueur)
        joueurs_avec_stats.append({
            'nom': nom_complet,
            'categorie': joueur['Catégorie'],
            'matchs': stats.get(nom_complet, 0)
        })
    
    # Trier par nombre de matchs (du moins au plus) puis aléatoirement pour les égalités
    joueurs_avec_stats.sort(key=lambda x: (x['matchs'], random.random()))
    
    # Créer des paires
    equipes = []
    round_num = get_current_round() + 1
    
    for i in range(0, len(joueurs_avec_stats), 2):
        if i + 1 < len(joueurs_avec_stats):
            j1 = joueurs_avec_stats[i]
            j2 = joueurs_avec_stats[i + 1]
            
            equipe_id = f"R{round_num}_E{i//2+1}"
            equipes.append({
                "Round": round_num,
                "ID": equipe_id,
                "Surnom": equipe_id,
                "J1": j1['nom'],
                "Cat1": j1['categorie'],
                "J2": j2['nom'],
                "Cat2": j2['categorie'],
                "Coeff": round((st.session_state.categories_dict.get(j1['categorie'], 1.0) +  
                               st.session_state.categories_dict.get(j2['categorie'], 1.0)) / 2, 3)
            })
        else:
            # Joueur impair -> avec joker
            j1 = joueurs_avec_stats[i]
            equipe_id = f"R{round_num}_E{i//2+1}"
            equipes.append({
                "Round": round_num,
                "ID": equipe_id,
                "Surnom": equipe_id,
                "J1": j1['nom'],
                "Cat1": j1['categorie'],
                "J2": f"Joker_R{round_num}",
                "Cat2": "Joker",
                "Coeff": round((st.session_state.categories_dict.get(j1['categorie'], 1.0) + 1.0) / 2, 3)
            })
            st.warning(f"⚠️ Joueur impair: {j1['nom']} avec Joker")
    
    # Sauvegarder dans l'historique
    df_equipes = pd.DataFrame(equipes)
    st.session_state.historique_equipes = pd.concat([
        st.session_state.historique_equipes,  
        df_equipes
    ], ignore_index=True)
    
    return equipes

def generer_round_individuel_equilibre():
    """Génère un round en mode individuel avec équilibrage"""
    if len(st.session_state.joueurs) < 2:
        st.error("Il faut au moins 2 joueurs")
        return False
    
    # Générer les équipes équilibrées
    equipes = generer_equipes_equilibrees()
    
    if not equipes:
        st.error("Impossible de générer les équipes")
        return False
    
    # Générer les matchs
    round_num = get_current_round() + 1
    nb_equipes = len(equipes)
    nb_terrains = st.session_state.nb_terrains
    matchs_possibles = min(nb_terrains, nb_equipes // 2)
    
    if matchs_possibles * 2 < nb_equipes:
        st.warning(f"⚠️ {nb_equipes} équipes pour {nb_terrains} terrains")
        st.warning(f"Seulement {matchs_possibles} matchs seront joués")
    
    # Créer les matchs
    matchs = []
    for i in range(0, min(nb_equipes, matchs_possibles * 2), 2):
        equipe_a = equipes[i]
        equipe_b = equipes[i + 1]
        
        matchs.append({
            "Round": round_num,
            "Terrain": f"T{i//2 + 1}",
            "Type": "normal",
            "Equipe_A_ID": equipe_a["ID"],
            "J1_A": equipe_a["J1"],
            "J2_A": equipe_a["J2"],
            "Score_A": 0,
            "Equipe_B_ID": equipe_b["ID"],
            "J1_B": equipe_b["J1"],
            "J2_B": equipe_b["J2"],
            "Score_B": 0,
            "Jokers": ""
        })
    
    # Ajouter aux matchs détaillés
    if matchs:
        df_matchs = pd.DataFrame(matchs)
        st.session_state.matchs_detail = pd.concat([
            st.session_state.matchs_detail,
            df_matchs
        ], ignore_index=True)
        
        # Synchroniser avec les matchs simplifiés
        for match in matchs:
            st.session_state.matchs = pd.concat([
                st.session_state.matchs,
                pd.DataFrame([{
                    "Round": match["Round"],
                    "Terrain": match["Terrain"],
                    "Type": match["Type"],
                    "Equipe A": match["Equipe_A_ID"],
                    "Score A": match["Score_A"],
                    "Equipe B": match["Equipe_B_ID"],
                    "Score B": match["Score_B"]
                }])
            ], ignore_index=True)
        
        st.success(f"✅ Round {round_num} généré avec {len(matchs)} matchs équilibrés!")
        return True
    
    return False

# === FONCTIONS POUR LA CLÔTURE DU TOURNOI ===

def analyser_retards_joueurs():
    """Analyse les retards des joueurs et retourne les statistiques"""
    stats = calculer_statistiques_joueurs()
    
    if not stats:
        return [], 0, {}
    
    # Trouver le nombre maximum de matchs joués
    max_matchs = max(stats.values()) if stats else 0
    
    # Identifier les joueurs en retard (au moins 1 match de moins)
    joueurs_en_retard = []
    retards = {}
    
    for joueur in st.session_state.joueurs:
        nom_complet = get_nom_complet(joueur)
        matchs_joues = stats.get(nom_complet, 0)
        
        if matchs_joues < max_matchs:
            retard = max_matchs - matchs_joues
            joueurs_en_retard.append(nom_complet)
            retards[nom_complet] = {
                'matchs': matchs_joues,
                'retard': retard,
                'categorie': joueur['Catégorie']
            }
    
    # Trier par retard décroissant
    joueurs_en_retard.sort(key=lambda x: retards[x]['retard'], reverse=True)
    
    return joueurs_en_retard, max_matchs, retards

def generer_round_rattrapage():
    """Génère un round de rattrapage POUR LES JOUEURS EN RETARD UNIQUEMENT"""
    # Analyser les retards
    joueurs_en_retard, max_matchs, retards = analyser_retards_joueurs()
    
    if not joueurs_en_retard:
        st.info("🎉 Tous les joueurs ont le même nombre de matchs! Aucun round de rattrapage nécessaire.")
        return None
    
    # Liste des joueurs SANS retard (potentiels jokers)
    joueurs_sans_retard = []
    for joueur in st.session_state.joueurs:
        nom_complet = get_nom_complet(joueur)
        if nom_complet not in joueurs_en_retard:
            joueurs_sans_retard.append({
                'nom': nom_complet,
                'categorie': joueur['Catégorie']
            })
    
    # Trier les joueurs en retard par retard décroissant (ceux avec le plus de retard en premier)
    joueurs_retard_tries = sorted(joueurs_en_retard, 
                                  key=lambda x: retards[x]['retard'], 
                                  reverse=True)
    
    # Créer les équipes UNIQUEMENT avec les joueurs en retard
    equipes = []
    joueurs_utilises = set()
    round_num = get_current_round() + 1
    
    # Premier passage : former des équipes avec 2 joueurs en retard
    for i in range(0, len(joueurs_retard_tries), 2):
        if i + 1 < len(joueurs_retard_tries):
            j1 = joueurs_retard_tries[i]
            j2 = joueurs_retard_tries[i + 1]
            
            if j1 not in joueurs_utilises and j2 not in joueurs_utilises:
                equipe_id = f"R{round_num}_RAT{i//2+1}"
                equipes.append({
                    "Round": round_num,
                    "ID": equipe_id,
                    "Surnom": f"Rattrapage_{i//2+1}",
                    "J1": j1,
                    "Cat1": retards[j1]['categorie'],
                    "J2": j2,
                    "Cat2": retards[j2]['categorie'],
                    "Coeff": round((st.session_state.categories_dict.get(retards[j1]['categorie'], 1.0) +  
                                   st.session_state.categories_dict.get(retards[j2]['categorie'], 1.0)) / 2, 3),
                    "Type": "rattrapage",
                    "JoueursRetard": [j1, j2],  # Les deux joueurs sont en retard
                    "Jokers": []  # Pas de jokers dans cette équipe
                })
                joueurs_utilises.update([j1, j2])
    
    # Gérer le dernier joueur en retard si nombre impair
    joueurs_retard_restants = [j for j in joueurs_retard_tries if j not in joueurs_utilises]
    
    if joueurs_retard_restants:
        # Il reste un joueur en retard sans partenaire
        j_retard_seul = joueurs_retard_restants[0]
        
        # Chercher un joker parmi les joueurs sans retard
        joker_trouve = None
        for joker in joueurs_sans_retard:
            if joker['nom'] not in joueurs_utilises:
                joker_trouve = joker
                break
        
        if joker_trouve:
            # Créer une équipe avec le joueur en retard et un joker
            equipe_id = f"R{round_num}_RAT{len(equipes)+1}"
            equipes.append({
                "Round": round_num,
                "ID": equipe_id,
                "Surnom": f"Rattrapage_{len(equipes)+1}",
                "J1": j_retard_seul,
                "Cat1": retards[j_retard_seul]['categorie'],
                "J2": joker_trouve['nom'],
                "Cat2": joker_trouve['categorie'],
                "Coeff": round((st.session_state.categories_dict.get(retards[j_retard_seul]['categorie'], 1.0) +  
                               st.session_state.categories_dict.get(joker_trouve['categorie'], 1.0)) / 2, 3),
                "Type": "rattrapage",
                "JoueursRetard": [j_retard_seul],  # Seul le premier joueur est en retard
                "Jokers": [joker_trouve['nom']]  # Le deuxième joueur est un joker
            })
            joueurs_utilises.update([j_retard_seul, joker_trouve['nom']])
        else:
            # Aucun joker disponible, on ne peut pas créer l'équipe
            st.warning(f"⚠️ Impossible de trouver un joker pour le joueur {j_retard_seul}")
    
    # Maintenant, nous avons des équipes composées soit de:
    # 1. Deux joueurs en retard
    # 2. Un joueur en retard + un joker (joueur sans retard)
    
    # Limiter le nombre de matchs aux terrains disponibles
    nb_terrains = st.session_state.nb_terrains
    nb_matchs_possibles = min(len(equipes) // 2, nb_terrains)
    
    if nb_matchs_possibles == 0:
        st.warning("⚠️ Pas assez d'équipes pour créer un match")
        return None
    
    # Sélectionner les équipes pour les matchs (prendre les premières équipes)
    equipes_selectionnees = equipes[:nb_matchs_possibles * 2]
    
    # Créer les matchs
    matchs = []
    for i in range(0, len(equipes_selectionnees), 2):
        equipe_a = equipes_selectionnees[i]
        equipe_b = equipes_selectionnees[i + 1]
        
        # Identifier les jokers pour ce match
        jokers_match = equipe_a.get("Jokers", []) + equipe_b.get("Jokers", [])
        
        matchs.append({
            "Round": round_num,
            "Terrain": f"T{i//2 + 1}",
            "Type": "rattrapage",
            "Equipe_A_ID": equipe_a["ID"],
            "J1_A": equipe_a["J1"],
            "J2_A": equipe_a["J2"],
            "Score_A": 0,
            "Equipe_B_ID": equipe_b["ID"],
            "J1_B": equipe_b["J1"],
            "J2_B": equipe_b["J2"],
            "Score_B": 0,
            "Jokers": ",".join(jokers_match) if jokers_match else ""
        })
    
    # Afficher des statistiques
    joueurs_retard_match = sum(len(eq.get("JoueursRetard", [])) for eq in equipes_selectionnees)
    joueurs_jokers_match = sum(len(eq.get("Jokers", [])) for eq in equipes_selectionnees)
    
    st.info(f"""
    **Résumé du round de rattrapage:**
    - {len(equipes_selectionnees)} équipes formées
    - {joueurs_retard_match} joueurs en retard programmés
    - {joueurs_jokers_match} joker(s) utilisé(s)
    - {len(matchs)} match(s) créé(s) sur {nb_terrains} terrain(s) disponible(s)
    """)
    
    return matchs

def generer_derniers_rounds():
    """Génère tous les rounds nécessaires pour équilibrer les matchs joués"""
    st.session_state.generating_final_rounds = True
    
    rounds_generes = []
    
    # Continuer tant qu'il y a des joueurs en retard
    while True:
        # Analyser la situation actuelle
        joueurs_en_retard, max_matchs, retards = analyser_retards_joueurs()
        
        if not joueurs_en_retard:
            break
        
        # Générer un round de rattrapage
        matchs_rattrapage = generer_round_rattrapage()
        
        if not matchs_rattrapage:
            break
        
        # Ajouter les matchs
        df_matchs = pd.DataFrame(matchs_rattrapage)
        st.session_state.matchs_detail = pd.concat([
            st.session_state.matchs_detail,
            df_matchs
        ], ignore_index=True)
        
        # Synchroniser avec les matchs simplifiés
        for match in matchs_rattrapage:
            st.session_state.matchs = pd.concat([
                st.session_state.matchs,
                pd.DataFrame([{
                    "Round": match["Round"],
                    "Terrain": match["Terrain"],
                    "Type": match["Type"],
                    "Equipe A": match["Equipe_A_ID"],
                    "Score A": match["Score_A"],
                    "Equipe B": match["Equipe_B_ID"],
                    "Score B": match["Score_B"]
                }])
            ], ignore_index=True)
        
        rounds_generes.append(matchs_rattrapage)
        
        # Mettre à jour l'historique des équipes pour ce round
        round_num = matchs_rattrapage[0]["Round"]
        
        # Récupérer toutes les équipes uniques de ce round
        equipes_round = []
        for match in matchs_rattrapage:
            # Équipe A
            equipes_round.append({
                "Round": round_num,
                "ID": match["Equipe_A_ID"],
                "Surnom": match["Equipe_A_ID"],
                "J1": match["J1_A"],
                "Cat1": get_categorie_joueur(match["J1_A"]),
                "J2": match["J2_A"],
                "Cat2": get_categorie_joueur(match["J2_A"]),
                "Coeff": round((st.session_state.categories_dict.get(get_categorie_joueur(match["J1_A"]), 1.0) +  
                               st.session_state.categories_dict.get(get_categorie_joueur(match["J2_A"]), 1.0)) / 2, 3)
            })
            
            # Équipe B
            equipes_round.append({
                "Round": round_num,
                "ID": match["Equipe_B_ID"],
                "Surnom": match["Equipe_B_ID"],
                "J1": match["J1_B"],
                "Cat1": get_categorie_joueur(match["J1_B"]),
                "J2": match["J2_B"],
                "Cat2": get_categorie_joueur(match["J2_B"]),
                "Coeff": round((st.session_state.categories_dict.get(get_categorie_joueur(match["J1_B"]), 1.0) +  
                               st.session_state.categories_dict.get(get_categorie_joueur(match["J2_B"]), 1.0)) / 2, 3)
            })
        
        # Ajouter à l'historique
        df_equipes = pd.DataFrame(equipes_round)
        st.session_state.historique_equipes = pd.concat([
            st.session_state.historique_equipes,
            df_equipes
        ], ignore_index=True)
        
        # Limiter à 10 rounds maximum pour éviter les boucles infinies
        if len(rounds_generes) >= 10:
            st.warning("⚠️ Limite de 10 rounds de rattrapage atteinte")
            break
    
    st.session_state.generating_final_rounds = False
    
    if rounds_generes:
        total_matchs = sum(len(r) for r in rounds_generes)
        st.success(f"✅ {len(rounds_generes)} round(s) de rattrapage généré(s) avec {total_matchs} matchs!")
        
        # Afficher un récapitulatif
        with st.expander("📊 Récapitulatif des rounds de rattrapage"):
            for i, round_matchs in enumerate(rounds_generes, 1):
                st.write(f"**Round de rattrapage {i}:** {len(round_matchs)} match(s)")
                for match in round_matchs:
                    jokers = match['Jokers'].split(',') if match['Jokers'] else []
                    jokers_text = f" (Jokers: {', '.join(jokers)})" if jokers else ""
                    st.write(f"  - {match['Equipe_A_ID']} vs {match['Equipe_B_ID']}{jokers_text}")
        
        return True
    else:
        st.info("Aucun round de rattrapage nécessaire")
        return False

# === CLASSEMENT INDIVIDUEL AVEC GESTION DES JOKERS ===

def calculer_classement_individuel_avec_jokers():
    """Calcule le classement individuel en excluant les points des jokers dans les matchs de rattrapage"""
    if st.session_state.matchs_detail.empty:
        return pd.DataFrame()
    
    # Initialiser les stats pour tous les joueurs
    stats_joueurs = {}
    
    # Initialiser avec les joueurs inscrits
    for joueur in st.session_state.joueurs:
        nom_complet = get_nom_complet(joueur)
        if nom_complet not in stats_joueurs:
            stats_joueurs[nom_complet] = {
                "Joueur": nom_complet,
                "Catégorie": joueur['Catégorie'],
                "Matchs Joués": 0,
                "Points Marqués": 0,
                "Points Encaissés": 0,
                "Différence": 0,
                "Score Pondéré": 0.0
            }
    
    # Parcourir tous les matchs détaillés
    for _, match in st.session_state.matchs_detail.iterrows():
        # Ignorer les matchs non joués
        if match["Score_A"] == 0 and match["Score_B"] == 0:
            continue
        
        # Identifier les jokers pour ce match
        jokers = match['Jokers'].split(',') if match['Jokers'] else []
        
        # Points pour les deux équipes
        points_a = match["Score_A"]
        points_b = match["Score_B"]
        
        # Équipe A
        joueurs_a = [match['J1_A'], match['J2_A']]
        for joueur_nom in joueurs_a:
            if joueur_nom and joueur_nom in stats_joueurs:
                stats = stats_joueurs[joueur_nom]
                
                # Vérifier si le joueur est un joker dans un match de rattrapage
                if match["Type"] == "rattrapage" and joueur_nom in jokers:
                    # Ne pas compter les stats pour les jokers dans les matchs de rattrapage
                    continue
                
                stats["Matchs Joués"] += 1
                stats["Points Marqués"] += points_a
                stats["Points Encaissés"] += points_b
                diff_match = points_a - points_b
                stats["Différence"] += diff_match
                
                # Calcul pondéré
                if st.session_state.algo_classement_individuel == "Pondéré":
                    coeff = 1.0
                    # Récupérer le coefficient du joueur
                    for j in st.session_state.joueurs:
                        if get_nom_complet(j) == joueur_nom:
                            coeff = st.session_state.categories_dict.get(j['Catégorie'], 1.0)
                            break
                    stats["Score Pondéré"] += diff_match * coeff
                else:
                    stats["Score Pondéré"] += diff_match
        
        # Équipe B
        joueurs_b = [match['J1_B'], match['J2_B']]
        for joueur_nom in joueurs_b:
            if joueur_nom and joueur_nom in stats_joueurs:
                stats = stats_joueurs[joueur_nom]
                
                # Vérifier si le joueur est un joker dans un match de rattrapage
                if match["Type"] == "rattrapage" and joueur_nom in jokers:
                    # Ne pas compter les stats pour les jokers dans les matchs de rattrapage
                    continue
                
                stats["Matchs Joués"] += 1
                stats["Points Marqués"] += points_b
                stats["Points Encaissés"] += points_a
                diff_match = points_b - points_a
                stats["Différence"] += diff_match
                
                # Calcul pondéré
                if st.session_state.algo_classement_individuel == "Pondéré":
                    coeff = 1.0
                    # Récupérer le coefficient du joueur
                    for j in st.session_state.joueurs:
                        if get_nom_complet(j) == joueur_nom:
                            coeff = st.session_state.categories_dict.get(j['Catégorie'], 1.0)
                            break
                    stats["Score Pondéré"] += diff_match * coeff
                else:
                    stats["Score Pondéré"] += diff_match
    
    # Convertir en DataFrame
    classement_data = []
    for joueur_nom, stats in stats_joueurs.items():
        if stats["Matchs Joués"] > 0:
            classement_data.append({
                "Joueur": stats["Joueur"],
                "Catégorie": stats["Catégorie"],
                "MJ": stats["Matchs Joués"],
                "PM": stats["Points Marqués"],
                "PE": stats["Points Encaissés"],
                "Diff": stats["Différence"],
                "Score": round(stats["Score Pondéré"], 2)
            })
    
    if not classement_data:
        return pd.DataFrame()
    
    df_classement = pd.DataFrame(classement_data)
    
    # Trier par score (décroissant), puis par différence, puis par points marqués
    df_classement = df_classement.sort_values(
        by=["Score", "Diff", "PM"], 
        ascending=[False, False, False]
    )
    
    # Réinitialiser l'index pour avoir le rang
    df_classement.index = range(1, len(df_classement) + 1)
    df_classement.index.name = "Rang"
    
    return df_classement

def afficher_statistiques_equilibre():
    """Affiche les statistiques d'équilibre des matchs joués"""
    stats = calculer_statistiques_joueurs()
    
    if not stats:
        st.info("Aucune statistique disponible")
        return
    
    # Créer un DataFrame pour l'affichage
    stats_list = []
    for joueur in st.session_state.joueurs:
        nom_complet = get_nom_complet(joueur)
        matchs_joues = stats.get(nom_complet, 0)
        stats_list.append({
            "Joueur": nom_complet,
            "Catégorie": joueur['Catégorie'],
            "Matchs Joués": matchs_joues
        })
    
    df_stats = pd.DataFrame(stats_list)
    df_stats = df_stats.sort_values(by="Matchs Joués", ascending=False)
    
    # Calculer des statistiques globales
    if stats:
        max_matchs = max(stats.values())
        min_matchs = min(stats.values())
        moyenne_matchs = sum(stats.values()) / len(stats) if stats else 0
        
        st.metric("Matchs maximum", max_matchs)
        st.metric("Matchs minimum", min_matchs)
        st.metric("Écart", max_matchs - min_matchs)
        st.metric("Moyenne", f"{moyenne_matchs:.1f}")
    
    return df_stats

# === FONCTIONS DE GÉNÉRATION POUR LE MODE CLASSIQUE ===

def generer_paires_equilibrees(mode="nouveau"):
    """Génère des paires équilibrées pour le mode classique"""
    # Fonction existante adaptée
    ja = [j for j in st.session_state.joueurs if j['Prénom'].strip() and j['Nom'].strip() and j['Catégorie']!="Joker"]
    
    if mode=="nouveau":
        if len(ja)<2:
            st.error("Il faut au moins 2 joueurs")
            return
        st.session_state.equipes_fixes = pd.DataFrame(columns=["ID", "Surnom", "J1", "Cat1", "J2", "Cat2", "Coeff"])
    else:
        if len(ja)<1:
            st.error("Aucun joueur non affecté")
            return
    
    # Trier par catégorie
    jt = sorted(ja, key=lambda x: st.session_state.categories_dict[x['Catégorie']], reverse=True)
    jaj = jt.pop() if len(jt)%2 else None
    
    # Créer les paires
    pairs = []
    while len(jt)>=2:
        pairs.append((jt.pop(0), jt.pop(-1)))
    
    # Déterminer le prochain ID
    if mode=="nouveau" or st.session_state.equipes_fixes.empty:
        sid = 1
    else:
        ids_existants = [int(e.replace("Équipe ", "")) for e in st.session_state.equipes_fixes["ID"] 
                        if isinstance(e, str) and e.startswith("Équipe ")]
        sid = max(ids_existants) + 1 if ids_existants else 1
    
    # Créer les équipes
    nouvelles_equipes = []
    for i, (p1, p2) in enumerate(pairs, sid):
        c1, c2 = p1['Catégorie'], p2['Catégorie']
        eid = f"Équipe {i}"
        nouvelles_equipes.append({
            "ID": eid,
            "Surnom": eid,
            "J1": get_nom_complet(p1),
            "Cat1": c1,
            "J2": get_nom_complet(p2),
            "Cat2": c2,
            "Coeff": round((st.session_state.categories_dict[c1] + st.session_state.categories_dict[c2]) / 2, 3)
        })
    
    # Gérer le joueur impair
    if jaj:
        i = sid + len(pairs)
        eid = f"Équipe {i}"
        c1 = jaj['Catégorie']
        nouvelles_equipes.append({
            "ID": eid,
            "Surnom": eid,
            "J1": get_nom_complet(jaj),
            "Cat1": c1,
            "J2": f"Joker {i}",
            "Cat2": "Joker",
            "Coeff": round((st.session_state.categories_dict[c1] + 1.0) / 2, 3)
        })
        st.warning(f"⚠️ Joueur impair: {get_nom_complet(jaj)} avec Joker")
    
    # Ajouter les équipes
    if nouvelles_equipes:
        df_nouvelles = pd.DataFrame(nouvelles_equipes)
        if mode == "ajouter":
            st.session_state.equipes_fixes = pd.concat([st.session_state.equipes_fixes, df_nouvelles], ignore_index=True)
        else:
            st.session_state.equipes_fixes = df_nouvelles
        st.success(f"✅ {len(nouvelles_equipes)} équipes {'ajoutées' if mode=='ajouter' else 'créées'}!")

def generer_round_classique():
    """Génère un round pour le mode classique"""
    if st.session_state.equipes_fixes.empty:
        st.error("Générez d'abord les équipes")
        return
    
    equipes_ids = st.session_state.equipes_fixes["ID"].tolist()
    
    # Compter les matchs déjà joués par chaque équipe
    matchs_par_equipe = {eid: 0 for eid in equipes_ids}
    adversaires_joues = {eid: set() for eid in equipes_ids}
    
    if not st.session_state.matchs.empty:
        for _, match in st.session_state.matchs.iterrows():
            matchs_par_equipe[match["Equipe A"]] += 1
            matchs_par_equipe[match["Equipe B"]] += 1
            adversaires_joues[match["Equipe A"]].add(match["Equipe B"])
            adversaires_joues[match["Equipe B"]].add(match["Equipe A"])
    
    # Trier les équipes par nombre de matchs joués (du moins au plus)
    equipes_triees = sorted(equipes_ids, key=lambda x: (matchs_par_equipe[x], random.random()))
    
    # Créer les matchs
    matchs = []
    equipes_utilisees = set()
    round_num = get_current_round() + 1
    
    for i, equipe_a in enumerate(equipes_triees):
        if equipe_a in equipes_utilisees:
            continue
        
        # Chercher un adversaire qui n'a pas encore joué contre cette équipe
        for equipe_b in equipes_triees[i+1:]:
            if equipe_b in equipes_utilisees:
                continue
            
            if equipe_b not in adversaires_joues[equipe_a]:
                # Créer le match
                matchs.append({
                    "Round": round_num,
                    "Terrain": f"T{len(matchs) + 1}",
                    "Type": "normal",
                    "Equipe_A_ID": equipe_a,
                    "J1_A": "",
                    "J2_A": "",
                    "Score_A": 0,
                    "Equipe_B_ID": equipe_b,
                    "J1_B": "",
                    "J2_B": "",
                    "Score_B": 0,
                    "Jokers": ""
                })
                
                equipes_utilisees.update([equipe_a, equipe_b])
                break
        
        # Limiter au nombre de terrains disponibles
        if len(matchs) >= st.session_state.nb_terrains:
            break
    
    # Remplir les informations des joueurs pour chaque match
    for match in matchs:
        # Équipe A
        equipe_a_info = st.session_state.equipes_fixes[st.session_state.equipes_fixes["ID"] == match["Equipe_A_ID"]]
        if not equipe_a_info.empty:
            equipe_a_info = equipe_a_info.iloc[0]
            match["J1_A"] = equipe_a_info["J1"]
            match["J2_A"] = equipe_a_info["J2"]
        
        # Équipe B
        equipe_b_info = st.session_state.equipes_fixes[st.session_state.equipes_fixes["ID"] == match["Equipe_B_ID"]]
        if not equipe_b_info.empty:
            equipe_b_info = equipe_b_info.iloc[0]
            match["J1_B"] = equipe_b_info["J1"]
            match["J2_B"] = equipe_b_info["J2"]
    
    # Ajouter les matchs
    if matchs:
        df_matchs = pd.DataFrame(matchs)
        st.session_state.matchs_detail = pd.concat([
            st.session_state.matchs_detail,
            df_matchs
        ], ignore_index=True)
        
        # Synchroniser avec les matchs simplifiés
        for match in matchs:
            st.session_state.matchs = pd.concat([
                st.session_state.matchs,
                pd.DataFrame([{
                    "Round": match["Round"],
                    "Terrain": match["Terrain"],
                    "Type": match["Type"],
                    "Equipe A": match["Equipe_A_ID"],
                    "Score A": match["Score_A"],
                    "Equipe B": match["Equipe_B_ID"],
                    "Score B": match["Score_B"]
                }])
            ], ignore_index=True)
        
        st.success(f"✅ Round {round_num} généré avec {len(matchs)} matchs!")
    else:
        st.warning("Impossible de créer de nouveaux matchs (toutes les combinaisons ont été jouées)")

# === FONCTION PRINCIPALE DE GÉNÉRATION DE ROUND ===

def generer_round():
    """Fonction principale pour générer un round selon le mode"""
    if st.session_state.mode_tournoi == "Classique":
        generer_round_classique()
    else:
        generer_round_individuel_equilibre()

# === INITIALISATION ===

# Initialiser les variables de session
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# === INTERFACE UTILISATEUR ===

st.set_page_config(layout="wide", page_title="Duck Manager Pro")
set_background(st.session_state.bg_image_data)

st.title(f"🏸 {st.session_state.nom_tournoi}")

# Barre latérale
with st.sidebar:
    st.header("👤 Profil")
    profil = st.radio("Profil:", ["Joueur", "Organisateur"], 
                     index=0 if st.session_state.profil == "Joueur" else 1)
    
    if profil == "Organisateur" and st.session_state.profil == "Joueur":
        mdp = st.text_input("Mot de passe:", type="password")
        if st.button("🔓 Valider"):
            if mdp.upper() == MOT_DE_PASSE_ORGANISATEUR:
                st.session_state.profil = "Organisateur"
                st.success("✅ Mode Organisateur activé!")
                st.rerun()
            else:
                st.error("❌ Mot de passe incorrect!")
    elif profil == "Joueur" and st.session_state.profil == "Organisateur":
        st.session_state.profil = "Joueur"
        st.rerun()
    
    st.divider()
    
    # Indicateur du mode
    if st.session_state.mode_tournoi == "Classique":
        st.success("🏆 **Mode Classique**")
        st.caption("Équipes fixes, classement par équipe")
    else:
        st.warning("🎯 **Mode Individuel**")
        st.caption("Équipes variables, priorité aux moins actifs")
    
    st.divider()
    
    # Statistiques rapides
    if st.session_state.joueurs:
        st.metric("Joueurs inscrits", len(st.session_state.joueurs))
    
    if not st.session_state.matchs.empty:
        st.metric("Rounds joués", get_current_round())
        st.metric("Matchs joués", len(st.session_state.matchs))
def exporter_joueurs_en_attente_pdf():
    """Génère un PDF avec la liste des joueurs en attente de validation"""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    
    # Titre
    elements.append(Paragraph(f"Joueurs en attente - {st.session_state.nom_tournoi}", styles['Title']))
    elements.append(Paragraph(f"Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # Table des joueurs
    if st.session_state.temp_joueurs:
        data = [["#", "Prénom", "Nom", "Catégorie"]]
        for idx, joueur in enumerate(st.session_state.temp_joueurs, 1):
            data.append([str(idx), joueur["Prénom"], joueur["Nom"], joueur["Catégorie"]])
        
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 0), (-1, -1), 10)
        ]))
        elements.append(table)
    else:
        elements.append(Paragraph("Aucun joueur en attente de validation", styles['Normal']))
    
    doc.build(elements)
    buf.seek(0)
    return buf

def exporter_joueurs_valides_pdf():
    """Génère un PDF avec la liste des joueurs validés"""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    
    # Titre
    elements.append(Paragraph(f"Joueurs validés - {st.session_state.nom_tournoi}", styles['Title']))
    elements.append(Paragraph(f"Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']))
    elements.append(Paragraph(f"Total: {len(st.session_state.joueurs)} joueurs", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # Table des joueurs
    if st.session_state.joueurs:
        data = [["#", "Prénom", "Nom", "Catégorie", "Matchs joués"]]
        
        # Calculer les matchs joués pour chaque joueur
        stats = calculer_statistiques_joueurs()
        
        for idx, joueur in enumerate(st.session_state.joueurs, 1):
            nom_complet = f"{joueur['Prénom']} {joueur['Nom']}"
            matchs_joues = stats.get(nom_complet, 0)
            data.append([str(idx), joueur["Prénom"], joueur["Nom"], joueur["Catégorie"], str(matchs_joues)])
        
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 0), (-1, -1), 10)
        ]))
        elements.append(table)
    else:
        elements.append(Paragraph("Aucun joueur validé", styles['Normal']))
    
    doc.build(elements)
    buf.seek(0)
    return buf

def exporter_joueurs_complet_xlsx():
    """Génère un fichier Excel avec tous les joueurs (en attente + validés) avec statut"""
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Feuille 1: Joueurs validés
        if st.session_state.joueurs:
            df_valides = pd.DataFrame(st.session_state.joueurs)
            # Ajouter les statistiques
            stats = calculer_statistiques_joueurs()
            df_valides['Matchs joués'] = df_valides.apply(
                lambda row: stats.get(f"{row['Prénom']} {row['Nom']}", 0), axis=1
            )
            # Ajouter la colonne Statut en fin de tableau
            df_valides['Statut'] = 'Validé'
            df_valides.to_excel(writer, sheet_name='Joueurs validés', index=False)
        
        # Feuille 2: Joueurs en attente
        if st.session_state.temp_joueurs:
            df_attente = pd.DataFrame(st.session_state.temp_joueurs)
            # Ajouter la colonne Statut en fin de tableau
            df_attente['Statut'] = 'En attente de validation'
            df_attente.to_excel(writer, sheet_name='Joueurs en attente', index=False)
        
        # Feuille 3: Liste complète avec statut (fusion des deux listes)
        liste_complete = []
        
        # Ajouter les joueurs validés
        for joueur in st.session_state.joueurs:
            nom_complet = f"{joueur['Prénom']} {joueur['Nom']}"
            stats = calculer_statistiques_joueurs()
            matchs_joues = stats.get(nom_complet, 0)
            
            liste_complete.append({
                'Prénom': joueur['Prénom'],
                'Nom': joueur['Nom'],
                'Catégorie': joueur['Catégorie'],
                'Matchs joués': matchs_joues,
                'Statut': 'Validé'
            })
        
        # Ajouter les joueurs en attente
        for joueur in st.session_state.temp_joueurs:
            liste_complete.append({
                'Prénom': joueur['Prénom'],
                'Nom': joueur['Nom'],
                'Catégorie': joueur['Catégorie'],
                'Matchs joués': 0,  # Pas encore joué
                'Statut': 'En attente de validation'
            })
        
        if liste_complete:
            df_complet = pd.DataFrame(liste_complete)
            # Trier par statut puis par nom
            df_complet = df_complet.sort_values(by=['Statut', 'Nom', 'Prénom'])
            df_complet.to_excel(writer, sheet_name='Liste complète', index=False)
        
        # Feuille 4: Résumé avec statistiques
        summary_data = {
            'Statistique': ['Joueurs validés', 'Joueurs en attente', 'Total joueurs'],
            'Valeur': [
                len(st.session_state.joueurs),
                len(st.session_state.temp_joueurs),
                len(st.session_state.joueurs) + len(st.session_state.temp_joueurs)
            ]
        }
        df_summary = pd.DataFrame(summary_data)
        df_summary.to_excel(writer, sheet_name='Résumé', index=False)
        
        # Feuille 5: Détail par catégorie
        categories_data = {}
        
        # Compter par catégorie pour les joueurs validés
        for joueur in st.session_state.joueurs:
            cat = joueur['Catégorie']
            categories_data[cat] = categories_data.get(cat, 0) + 1
        
        # Compter par catégorie pour les joueurs en attente
        for joueur in st.session_state.temp_joueurs:
            cat = joueur['Catégorie']
            categories_data[cat] = categories_data.get(cat, 0) + 1
        
        if categories_data:
            df_categories = pd.DataFrame({
                'Catégorie': list(categories_data.keys()),
                'Nombre de joueurs': list(categories_data.values())
            })
            df_categories = df_categories.sort_values(by='Nombre de joueurs', ascending=False)
            df_categories.to_excel(writer, sheet_name='Par catégorie', index=False)
    
    output.seek(0)
    return output.getvalue()

def exporter_equipes_actuelles_pdf():
    """Génère un PDF avec les équipes actuelles"""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    
    # Titre
    elements.append(Paragraph(f"Équipes actuelles - {st.session_state.nom_tournoi}", styles['Title']))
    elements.append(Paragraph(f"Mode: {st.session_state.mode_tournoi}", styles['Normal']))
    elements.append(Paragraph(f"Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # Récupérer les équipes actuelles selon le mode
    equipes_actuelles = get_equipes_actuelles()
    
    if not equipes_actuelles.empty:
        data = [["ID", "Surnom", "Joueur 1", "Cat1", "Joueur 2", "Cat2", "Coeff"]]
        
        for _, equipe in equipes_actuelles.iterrows():
            data.append([
                equipe['ID'],
                get_nom_affichage_equipe(equipe),
                equipe['J1'],
                equipe['Cat1'],
                equipe['J2'],
                equipe['Cat2'],
                f"{equipe['Coeff']:.3f}"
            ])
        
        table = Table(data, colWidths=[60, 60, 80, 40, 80, 40, 40])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 0), (-1, -1), 9)
        ]))
        elements.append(table)
    else:
        elements.append(Paragraph("Aucune équipe actuelle", styles['Normal']))
    
    doc.build(elements)
    buf.seek(0)
    return buf

def exporter_historique_equipes_pdf():
    """Génère un PDF avec l'historique des équipes (mode individuel)"""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    
    # Titre
    elements.append(Paragraph(f"Historique des équipes - {st.session_state.nom_tournoi}", styles['Title']))
    elements.append(Paragraph(f"Mode: {st.session_state.mode_tournoi}", styles['Normal']))
    elements.append(Paragraph(f"Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    if not st.session_state.historique_equipes.empty:
        # Grouper par round
        for round_num in sorted(st.session_state.historique_equipes["Round"].unique()):
            elements.append(Paragraph(f"Round {round_num}", styles['Heading2']))
            elements.append(Spacer(1, 10))
            
            equipes_round = st.session_state.historique_equipes[
                st.session_state.historique_equipes["Round"] == round_num
            ]
            
            data = [["ID", "Surnom", "Joueur 1", "Cat1", "Joueur 2", "Cat2", "Coeff"]]
            
            for _, equipe in equipes_round.iterrows():
                data.append([
                    equipe['ID'],
                    get_nom_affichage_equipe(equipe),
                    equipe['J1'],
                    equipe['Cat1'],
                    equipe['J2'],
                    equipe['Cat2'],
                    f"{equipe['Coeff']:.3f}"
                ])
            
            table = Table(data, colWidths=[60, 60, 80, 40, 80, 40, 40])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4B8BBE')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 0), (-1, -1), 8)
            ]))
            elements.append(table)
            elements.append(Spacer(1, 20))
    else:
        elements.append(Paragraph("Aucun historique d'équipes disponible", styles['Normal']))
    
    doc.build(elements)
    buf.seek(0)
    return buf

def exporter_equipes_complet_xlsx():
    """Génère un fichier Excel avec toutes les données d'équipes"""
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Feuille 1: Équipes actuelles
        equipes_actuelles = get_equipes_actuelles()
        if not equipes_actuelles.empty:
            equipes_actuelles.to_excel(writer, sheet_name='Équipes actuelles', index=False)
        
        # Feuille 2: Historique des équipes (mode individuel)
        if not st.session_state.historique_equipes.empty:
            st.session_state.historique_equipes.to_excel(writer, sheet_name='Historique équipes', index=False)
        
        # Feuille 3: Équipes fixes (mode classique)
        if not st.session_state.equipes_fixes.empty:
            st.session_state.equipes_fixes.to_excel(writer, sheet_name='Équipes fixes', index=False)
        
        # Feuille 4: Résumé
        summary_data = {
            'Statistique': ['Mode tournoi', 'Équipes actuelles', 'Équipes fixes', 'Rounds historisés'],
            'Valeur': [
                st.session_state.mode_tournoi,
                len(equipes_actuelles),
                len(st.session_state.equipes_fixes),
                len(st.session_state.historique_equipes["Round"].unique()) if not st.session_state.historique_equipes.empty else 0
            ]
        }
        df_summary = pd.DataFrame(summary_data)
        df_summary.to_excel(writer, sheet_name='Résumé', index=False)
    
    output.seek(0)
    return output.getvalue()

def exporter_matchs_en_cours_pdf():
    """Génère un PDF avec les matchs en cours (dernier round)"""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    
    # Titre
    elements.append(Paragraph(f"Matchs en cours - {st.session_state.nom_tournoi}", styles['Title']))
    elements.append(Paragraph(f"Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']))
    elements.append(Paragraph(f"Round actuel: {get_current_round()}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    if not st.session_state.matchs_detail.empty:
        # Récupérer le dernier round
        dernier_round = st.session_state.matchs_detail["Round"].max()
        matchs_round = st.session_state.matchs_detail[
            st.session_state.matchs_detail["Round"] == dernier_round
        ]
        
        if not matchs_round.empty:
            data = [["Terrain", "Type", "Équipe A", "Joueurs A", "Score A", "Score B", "Équipe B", "Joueurs B"]]
            
            for _, match in matchs_round.iterrows():
                # Formater les joueurs
                joueurs_a = f"{match['J1_A']}\n{match['J2_A']}"
                joueurs_b = f"{match['J1_B']}\n{match['J2_B']}"
                
                # Récupérer les noms d'équipes
                if st.session_state.mode_tournoi == "Classique":
                    eq_a = st.session_state.equipes_fixes[
                        st.session_state.equipes_fixes["ID"] == match["Equipe_A_ID"]
                    ]
                    eq_b = st.session_state.equipes_fixes[
                        st.session_state.equipes_fixes["ID"] == match["Equipe_B_ID"]
                    ]
                    nom_eq_a = get_nom_affichage_equipe(eq_a.iloc[0]) if not eq_a.empty else match["Equipe_A_ID"]
                    nom_eq_b = get_nom_affichage_equipe(eq_b.iloc[0]) if not eq_b.empty else match["Equipe_B_ID"]
                else:
                    nom_eq_a = match["Equipe_A_ID"]
                    nom_eq_b = match["Equipe_B_ID"]
                
                # Ajouter les jokers si présents
                type_match = match["Type"]
                if match["Jokers"]:
                    type_match = f"{match['Type']} (Jokers: {match['Jokers']})"
                
                data.append([
                    match["Terrain"],
                    type_match,
                    nom_eq_a,
                    joueurs_a,
                    str(match["Score_A"]),
                    str(match["Score_B"]),
                    nom_eq_b,
                    joueurs_b
                ])
            
            table = Table(data, colWidths=[40, 70, 60, 80, 30, 30, 60, 80])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4B8BBE')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('ALIGN', (3, 1), (3, -1), 'LEFT'),
                ('ALIGN', (7, 1), (7, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 0), (-1, -1), 8)
            ]))
            elements.append(table)
        else:
            elements.append(Paragraph("Aucun match en cours", styles['Normal']))
    else:
        elements.append(Paragraph("Aucun match enregistré", styles['Normal']))
    
    doc.build(elements)
    buf.seek(0)
    return buf

def exporter_tous_matchs_pdf():
    """Génère un PDF avec tous les matchs du tournoi avec les joueurs dans la même case"""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20, rightMargin=20)
    elements = []
    styles = getSampleStyleSheet()
    
    # Titre
    elements.append(Paragraph(f"Tous les matchs - {st.session_state.nom_tournoi}", styles['Title']))
    elements.append(Paragraph(f"Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']))
    elements.append(Paragraph(f"Total matchs: {len(st.session_state.matchs_detail)}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    if not st.session_state.matchs_detail.empty:
        # Grouper par round
        for round_num in sorted(st.session_state.matchs_detail["Round"].unique()):
            elements.append(Paragraph(f"Round {round_num}", styles['Heading2']))
            elements.append(Spacer(1, 10))
            
            matchs_round = st.session_state.matchs_detail[
                st.session_state.matchs_detail["Round"] == round_num
            ]
            
            # Créer les en-têtes de tableau avec les colonnes demandées
            data = [["Terrain", "Type", "Équipe A", "Joueurs A", "Score A", "Score B", "Équipe B", "Joueurs B"]]
            
            for _, match in matchs_round.iterrows():
                # Formater les joueurs (un sur l'autre)
                joueurs_a = f"{match['J1_A']}\n{match['J2_A']}"
                joueurs_b = f"{match['J1_B']}\n{match['J2_B']}"
                
                # Récupérer les noms d'équipes
                if st.session_state.mode_tournoi == "Classique":
                    eq_a = st.session_state.equipes_fixes[
                        st.session_state.equipes_fixes["ID"] == match["Equipe_A_ID"]
                    ]
                    eq_b = st.session_state.equipes_fixes[
                        st.session_state.equipes_fixes["ID"] == match["Equipe_B_ID"]
                    ]
                    nom_eq_a = get_nom_affichage_equipe(eq_a.iloc[0]) if not eq_a.empty else match["Equipe_A_ID"]
                    nom_eq_b = get_nom_affichage_equipe(eq_b.iloc[0]) if not eq_b.empty else match["Equipe_B_ID"]
                else:
                    # Mode Individuel : chercher dans l'historique
                    equipes_round_hist = get_equipes_par_round(round_num)
                    if not equipes_round_hist.empty:
                        eq_a = equipes_round_hist[equipes_round_hist["ID"] == match["Equipe_A_ID"]]
                        eq_b = equipes_round_hist[equipes_round_hist["ID"] == match["Equipe_B_ID"]]
                        nom_eq_a = get_nom_affichage_equipe(eq_a.iloc[0]) if not eq_a.empty else match["Equipe_A_ID"]
                        nom_eq_b = get_nom_affichage_equipe(eq_b.iloc[0]) if not eq_b.empty else match["Equipe_B_ID"]
                    else:
                        nom_eq_a = match["Equipe_A_ID"]
                        nom_eq_b = match["Equipe_B_ID"]
                
                # Ajouter les jokers si présents
                type_match = match["Type"]
                if match["Jokers"] and pd.notna(match["Jokers"]):
                    type_match = f"{match['Type']}\n(Jokers: {match['Jokers']})"
                
                data.append([
                    match["Terrain"],
                    type_match,
                    nom_eq_a,
                    joueurs_a,
                    str(match["Score_A"]),
                    str(match["Score_B"]),
                    nom_eq_b,
                    joueurs_b
                ])
            
            # Créer le tableau avec des largeurs de colonnes adaptées
            table = Table(data, colWidths=[35, 55, 60, 75, 30, 30, 60, 75])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4B8BBE')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('ALIGN', (3, 1), (3, -1), 'LEFT'),  # Alignement à gauche pour les joueurs
                ('ALIGN', (7, 1), (7, -1), 'LEFT'),  # Alignement à gauche pour les joueurs
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F0F0F0')])
            ]))
            elements.append(table)
            elements.append(Spacer(1, 20))
    else:
        elements.append(Paragraph("Aucun match enregistré", styles['Normal']))
    
    doc.build(elements)
    buf.seek(0)
    return buf

def exporter_matchs_complet_xlsx():
    """Génère un fichier Excel avec tous les matchs"""
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Feuille 1: Tous les matchs détaillés
        if not st.session_state.matchs_detail.empty:
            st.session_state.matchs_detail.to_excel(writer, sheet_name='Matchs détaillés', index=False)
        
        # Feuille 2: Matchs simplifiés
        if not st.session_state.matchs.empty:
            st.session_state.matchs.to_excel(writer, sheet_name='Matchs simplifiés', index=False)
        
        # Feuille 3: Statistiques des matchs
        summary_data = {
            'Statistique': ['Total matchs', 'Rounds joués', 'Matchs avec jokers', 'Dernier round'],
            'Valeur': [
                len(st.session_state.matchs_detail),
                len(st.session_state.matchs_detail["Round"].unique()) if not st.session_state.matchs_detail.empty else 0,
                len(st.session_state.matchs_detail[st.session_state.matchs_detail["Jokers"] != ""]) if not st.session_state.matchs_detail.empty else 0,
                get_current_round()
            ]
        }
        df_summary = pd.DataFrame(summary_data)
        df_summary.to_excel(writer, sheet_name='Statistiques', index=False)
    
    output.seek(0)
    return output.getvalue()

def exporter_statistiques_pdf():
    """Génère un PDF avec les statistiques du tournoi"""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    
    # Titre
    elements.append(Paragraph(f"Statistiques - {st.session_state.nom_tournoi}", styles['Title']))
    elements.append(Paragraph(f"Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']))
    elements.append(Paragraph(f"Mode: {st.session_state.mode_tournoi}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # Section 1: Statistiques générales
    elements.append(Paragraph("Statistiques générales", styles['Heading2']))
    elements.append(Spacer(1, 10))
    
    stats_data = [
        ["Joueurs inscrits", len(st.session_state.joueurs)],
        ["Joueurs en attente", len(st.session_state.temp_joueurs)],
        ["Rounds joués", get_current_round()],
        ["Matchs joués", len(st.session_state.matchs_detail)],
        ["Terrains disponibles", st.session_state.nb_terrains]
    ]
    
    if st.session_state.mode_tournoi == "Classique":
        stats_data.append(["Équipes fixes", len(st.session_state.equipes_fixes)])
    else:
        equipes_actuelles = get_equipes_actuelles()
        stats_data.append(["Équipes actuelles", len(equipes_actuelles)])
        stats_data.append(["Rounds historisés", len(st.session_state.historique_equipes["Round"].unique()) if not st.session_state.historique_equipes.empty else 0])
    
    table_stats = Table(stats_data, colWidths=[150, 100])
    table_stats.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4B8BBE')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(table_stats)
    elements.append(Spacer(1, 20))
    
    # Section 2: Statistiques d'équilibre (mode individuel)
    if st.session_state.mode_tournoi == "Individuel":
        elements.append(Paragraph("Équilibre des matchs joués", styles['Heading2']))
        elements.append(Spacer(1, 10))
        
        stats = calculer_statistiques_joueurs()
        if stats:
            # Calculer les statistiques
            max_matchs = max(stats.values()) if stats else 0
            min_matchs = min(stats.values()) if stats else 0
            moyenne_matchs = sum(stats.values()) / len(stats) if stats else 0
            ecart = max_matchs - min_matchs
            
            equil_data = [
                ["Matchs maximum", max_matchs],
                ["Matchs minimum", min_matchs],
                ["Écart", ecart],
                ["Moyenne", f"{moyenne_matchs:.1f}"]
            ]
            
            table_equil = Table(equil_data, colWidths=[150, 100])
            table_equil.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E8B57')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(table_equil)
            elements.append(Spacer(1, 10))
            
            # Liste des joueurs par nombre de matchs
            elements.append(Paragraph("Détail par joueur", styles['Heading3']))
            elements.append(Spacer(1, 10))
            
            joueurs_stats = []
            for joueur in st.session_state.joueurs:
                nom_complet = get_nom_complet(joueur)
                matchs_joues = stats.get(nom_complet, 0)
                joueurs_stats.append([nom_complet, joueur['Catégorie'], matchs_joues])
            
            # Trier par nombre de matchs décroissant
            joueurs_stats.sort(key=lambda x: x[2], reverse=True)
            
            detail_data = [["Joueur", "Catégorie", "Matchs joués"]]
            detail_data.extend(joueurs_stats)
            
            table_detail = Table(detail_data, colWidths=[120, 80, 50])
            table_detail.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (2, 1), (2, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 0), (-1, -1), 9)
            ]))
            elements.append(table_detail)
    
    doc.build(elements)
    buf.seek(0)
    return buf

def exporter_statistiques_xlsx():
    """Génère un fichier Excel avec toutes les statistiques"""
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Feuille 1: Statistiques générales
        general_data = {
            'Statistique': [
                'Nom du tournoi', 'Mode', 'Joueurs inscrits', 'Joueurs en attente',
                'Rounds joués', 'Matchs joués', 'Terrains disponibles'
            ],
            'Valeur': [
                st.session_state.nom_tournoi,
                st.session_state.mode_tournoi,
                len(st.session_state.joueurs),
                len(st.session_state.temp_joueurs),
                get_current_round(),
                len(st.session_state.matchs_detail),
                st.session_state.nb_terrains
            ]
        }
        df_general = pd.DataFrame(general_data)
        df_general.to_excel(writer, sheet_name='Statistiques générales', index=False)
        
        # Feuille 2: Statistiques d'équilibre (mode individuel)
        if st.session_state.mode_tournoi == "Individuel":
            stats = calculer_statistiques_joueurs()
            if stats:
                equil_data = []
                for joueur in st.session_state.joueurs:
                    nom_complet = get_nom_complet(joueur)
                    matchs_joues = stats.get(nom_complet, 0)
                    equil_data.append({
                        'Joueur': nom_complet,
                        'Catégorie': joueur['Catégorie'],
                        'Matchs joués': matchs_joues
                    })
                
                df_equil = pd.DataFrame(equil_data)
                df_equil = df_equil.sort_values(by='Matchs joués', ascending=False)
                df_equil.to_excel(writer, sheet_name='Équilibre matchs', index=False)
        
        # Feuille 3: Statistiques des équipes
        team_data = []
        if st.session_state.mode_tournoi == "Classique":
            if not st.session_state.equipes_fixes.empty:
                for _, equipe in st.session_state.equipes_fixes.iterrows():
                    team_data.append({
                        'ID': equipe['ID'],
                        'Surnom': get_nom_affichage_equipe(equipe),
                        'Joueur 1': equipe['J1'],
                        'Joueur 2': equipe['J2'],
                        'Coefficient': equipe['Coeff']
                    })
        else:
            equipes_actuelles = get_equipes_actuelles()
            if not equipes_actuelles.empty:
                for _, equipe in equipes_actuelles.iterrows():
                    team_data.append({
                        'ID': equipe['ID'],
                        'Surnom': get_nom_affichage_equipe(equipe),
                        'Joueur 1': equipe['J1'],
                        'Joueur 2': equipe['J2'],
                        'Coefficient': equipe['Coeff']
                    })
        
        if team_data:
            df_teams = pd.DataFrame(team_data)
            df_teams.to_excel(writer, sheet_name='Équipes', index=False)
    
    output.seek(0)
    return output.getvalue()

def exporter_classement_equipes_pdf():
    """Génère un PDF avec le classement par équipes (mode classique)"""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    
    # Titre
    elements.append(Paragraph(f"Classement par équipes - {st.session_state.nom_tournoi}", styles['Title']))
    elements.append(Paragraph(f"Mode: {st.session_state.algo_classement}", styles['Normal']))
    elements.append(Paragraph(f"Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    if st.session_state.mode_tournoi == "Classique" and not st.session_state.matchs.empty and not st.session_state.equipes_fixes.empty:
        # Calculer le classement
        stats = []
        for _, eq in st.session_state.equipes_fixes.iterrows():
            eid = eq["ID"]
            m_eq = st.session_state.matchs[
                (st.session_state.matchs["Equipe A"] == eid) | 
                (st.session_state.matchs["Equipe B"] == eid)
            ]
            
            pm, pe, v, n, d = 0, 0, 0, 0, 0
            for _, m in m_eq.iterrows():
                if m["Score A"] == 0 and m["Score B"] == 0:
                    continue
                
                is_a = m["Equipe A"] == eid
                ma, sa = (m["Score A"], m["Score B"]) if is_a else (m["Score B"], m["Score A"])
                
                pm += ma
                pe += sa
                
                if ma > sa:
                    v += 1
                elif ma == sa:
                    n += 1
                else:
                    d += 1
            
            diff = pm - pe
            if st.session_state.algo_classement == "Pondéré":
                score = round(((v * 3) + (n * 1)) * eq["Coeff"], 2)
            else:
                score = (v * 2) + (n * 1)
            
            stats.append({
                "Équipe": get_nom_affichage_equipe(eq),
                "Joueurs": f"{eq['J1']} & {eq['J2']}",
                "V": v, "N": n, "D": d,
                "PM": pm, "PE": pe, "Diff": diff,
                "Points": score
            })
        
        if stats:
            # Trier par points et différence
            stats.sort(key=lambda x: (x["Points"], x["Diff"]), reverse=True)
            
            data = [["Rang", "Équipe", "Joueurs", "V", "N", "D", "PM", "PE", "Diff", "Points"]]
            for idx, stat in enumerate(stats, 1):
                data.append([
                    str(idx),
                    stat["Équipe"],
                    stat["Joueurs"],
                    str(stat["V"]),
                    str(stat["N"]),
                    str(stat["D"]),
                    str(stat["PM"]),
                    str(stat["PE"]),
                    str(stat["Diff"]),
                    str(stat["Points"])
                ])
            
            table = Table(data, colWidths=[30, 70, 120, 20, 20, 20, 30, 30, 30, 40])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4B8BBE')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 0), (-1, -1), 8)
            ]))
            elements.append(table)
        else:
            elements.append(Paragraph("Aucune statistique disponible pour le classement", styles['Normal']))
    else:
        if st.session_state.mode_tournoi != "Classique":
            elements.append(Paragraph("Le classement par équipes n'est disponible qu'en mode Classique", styles['Normal']))
        else:
            elements.append(Paragraph("Aucun match joué pour le moment", styles['Normal']))
    
    doc.build(elements)
    buf.seek(0)
    return buf

def exporter_classement_individuel_pdf():
    """Génère un PDF avec le classement individuel"""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    
    # Titre
    elements.append(Paragraph(f"Classement individuel - {st.session_state.nom_tournoi}", styles['Title']))
    elements.append(Paragraph(f"Mode: {st.session_state.algo_classement_individuel}", styles['Normal']))
    elements.append(Paragraph(f"Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    df_classement = calculer_classement_individuel_avec_jokers()
    
    if not df_classement.empty:
        data = [["Rang", "Joueur", "Catégorie", "MJ", "PM", "PE", "Diff", "Score"]]
        
        for idx, row in df_classement.iterrows():
            data.append([
                str(idx),
                row["Joueur"],
                row["Catégorie"],
                str(row["MJ"]),
                str(row["PM"]),
                str(row["PE"]),
                str(row["Diff"]),
                str(row["Score"])
            ])
        
        table = Table(data, colWidths=[30, 120, 60, 30, 40, 40, 40, 50])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4B8BBE')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 0), (-1, -1), 8)
        ]))
        elements.append(table)
    else:
        elements.append(Paragraph("Aucun match joué pour le moment", styles['Normal']))
    
    doc.build(elements)
    buf.seek(0)
    return buf

def exporter_classements_complet_xlsx():
    """Génère un fichier Excel avec tous les classements"""
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Feuille 1: Classement individuel
        df_classement_indiv = calculer_classement_individuel_avec_jokers()
        if not df_classement_indiv.empty:
            df_classement_indiv.to_excel(writer, sheet_name='Classement individuel')
        
        # Feuille 2: Classement par équipes (mode classique)
        if st.session_state.mode_tournoi == "Classique" and not st.session_state.matchs.empty and not st.session_state.equipes_fixes.empty:
            # Calculer le classement par équipes
            stats = []
            for _, eq in st.session_state.equipes_fixes.iterrows():
                eid = eq["ID"]
                m_eq = st.session_state.matchs[
                    (st.session_state.matchs["Equipe A"] == eid) | 
                    (st.session_state.matchs["Equipe B"] == eid)
                ]
                
                pm, pe, v, n, d = 0, 0, 0, 0, 0
                for _, m in m_eq.iterrows():
                    if m["Score A"] == 0 and m["Score B"] == 0:
                        continue
                    
                    is_a = m["Equipe A"] == eid
                    ma, sa = (m["Score A"], m["Score B"]) if is_a else (m["Score B"], m["Score A"])
                    
                    pm += ma
                    pe += sa
                    
                    if ma > sa:
                        v += 1
                    elif ma == sa:
                        n += 1
                    else:
                        d += 1
                
                diff = pm - pe
                if st.session_state.algo_classement == "Pondéré":
                    score = round(((v * 3) + (n * 1)) * eq["Coeff"], 2)
                else:
                    score = (v * 2) + (n * 1)
                
                stats.append({
                    "Équipe": get_nom_affichage_equipe(eq),
                    "Joueurs": f"{eq['J1']} & {eq['J2']}",
                    "V": v, "N": n, "D": d,
                    "PM": pm, "PE": pe, "Diff": diff,
                    "Points": score
                })
            
            if stats:
                df_classement_eq = pd.DataFrame(stats)
                df_classement_eq = df_classement_eq.sort_values(by=["Points", "Diff"], ascending=False)
                df_classement_eq.index = range(1, len(df_classement_eq) + 1)
                df_classement_eq.index.name = "Rang"
                df_classement_eq.to_excel(writer, sheet_name='Classement équipes')
        
        # Feuille 3: Résumé des classements
        summary_data = {
            'Type classement': ['Individuel', 'Par équipes'],
            'Disponible': [
                'Oui' if not df_classement_indiv.empty else 'Non',
                'Oui (mode Classique)' if st.session_state.mode_tournoi == "Classique" else 'Non (mode Individuel)'
            ],
            'Nombre de lignes': [
                len(df_classement_indiv),
                len(st.session_state.equipes_fixes) if st.session_state.mode_tournoi == "Classique" else 0
            ],
            'Méthode de calcul': [
                st.session_state.algo_classement_individuel,
                st.session_state.algo_classement if st.session_state.mode_tournoi == "Classique" else 'N/A'
            ]
        }
        df_summary = pd.DataFrame(summary_data)
        df_summary.to_excel(writer, sheet_name='Résumé classements', index=False)
    
    output.seek(0)
    return output.getvalue()

# === NOUVELLES FONCTIONS POUR LES POPUPS DE CONFIRMATION ===

def afficher_popup_confirmation(titre, message, fonction_confirmation, key_suffix):
    """Affiche une popup de confirmation générique"""
    # Créer un conteneur pour la popup
    with st.container():
        st.markdown("""
        <style>
        .popup-overlay {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: rgba(0, 0, 0, 0.5);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }
        .popup-content {
            background-color: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            max-width: 500px;
            width: 90%;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Afficher le message d'avertissement
        st.warning(f"⚠️ {titre}")
        st.error(message)
        
        # Boutons de confirmation
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button(f"✅ Oui, confirmer", use_container_width=True, type="primary", key=f"confirm_{key_suffix}"):
                fonction_confirmation()
                st.rerun()
        
        with col2:
            if st.button("❌ Annuler", use_container_width=True, key=f"cancel_{key_suffix}"):
                st.session_state[f"show_popup_{key_suffix}"] = False
                st.rerun()

def reinitialiser_matchs_avec_confirmation():
    """Réinitialise les matchs avec confirmation"""
    st.session_state.matchs = pd.DataFrame(columns=["Round", "Terrain", "Type", "Equipe A", "Score A", "Equipe B", "Score B"])
    st.session_state.matchs_detail = pd.DataFrame(columns=[
        "Round", "Terrain", "Type", "Equipe_A_ID", "J1_A", "J2_A", "Score_A",
        "Equipe_B_ID", "J1_B", "J2_B", "Score_B", "Jokers"
    ])
    st.session_state.historique_equipes = pd.DataFrame(columns=["Round", "ID", "Surnom", "J1", "Cat1", "J2", "Cat2", "Coeff"])
    st.success("✅ Matchs réinitialisés!")
    st.session_state["show_popup_matchs"] = False

def reinitialiser_tournoi_avec_confirmation():
    """Réinitialise tout le tournoi avec confirmation"""
    for key in list(st.session_state.keys()):
        if key != 'profil':
            del st.session_state[key]
    
    # Réinitialiser avec les nouvelles structures
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val
    
    st.success("✅ Tournoi complètement réinitialisé!")
    st.session_state["show_popup_tournoi"] = False

def reinitialiser_matchs_simple_avec_confirmation():
    """Réinitialise seulement les matchs (sans historique équipes) avec confirmation"""
    st.session_state.matchs = pd.DataFrame(columns=["Round", "Terrain", "Type", "Equipe A", "Score A", "Equipe B", "Score B"])
    st.session_state.matchs_detail = pd.DataFrame(columns=[
        "Round", "Terrain", "Type", "Equipe_A_ID", "J1_A", "J2_A", "Score_A",
        "Equipe_B_ID", "J1_B", "J2_B", "Score_B", "Jokers"
    ])
    st.success("✅ Matchs réinitialisés!")
    st.session_state["show_popup_matchs_simple"] = False

# Ajouter les clés de popup aux defaults
defaults.update({
    'show_popup_matchs': False,
    'show_popup_tournoi': False,
    'show_popup_matchs_simple': False,
    'show_popup_import_matchs': False
})

# Onglets principaux
tabs = st.tabs(["👥 Joueurs", "🤝 Équipes", "🏸 Matchs", "📊 Statistiques", "🏆 Classements", "⚙️ Paramètres"])

# Onglet 1: Joueurs
with tabs[0]:
    st.header("👥 Gestion des Joueurs")
    
    # Formulaire d'ajout
    col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
    with col1:
        prenom = st.text_input("Prénom", key="prenom_input")
    with col2:
        nom = st.text_input("Nom", key="nom_input")
    with col3:
        categorie = st.selectbox("Catégorie", 
                                [c for c in st.session_state.categories_dict if c != "Joker"],
                                key="categorie_select")
    with col4:
        st.write("")  # Espacement
        st.write("")
        if st.button("➕ Ajouter", use_container_width=True):
            if prenom.strip() and nom.strip():
                if joueur_existe(prenom, nom):
                    st.error(f"❌ {prenom} {nom} existe déjà!")
                else:
                    st.session_state.temp_joueurs.append({
                        "Prénom": prenom.strip(),
                        "Nom": nom.strip(),
                        "Catégorie": categorie
                    })
                    st.success(f"✅ {prenom} {nom} ajouté en attente de validation")
                    st.rerun()
            else:
                st.error("❌ Prénom et nom requis!")
    
    # Joueurs en attente de validation
    if st.session_state.temp_joueurs:
        st.subheader("👥 Joueurs en attente de validation")
        
        if est_organisateur():
            col_val1, col_val2 = st.columns(2)
            with col_val1:
                if st.button("✅ Valider tous", use_container_width=True):
                    for joueur in st.session_state.temp_joueurs:
                        st.session_state.joueurs.append(joueur)
                    st.session_state.temp_joueurs = []
                    st.success("✅ Tous les joueurs validés!")
                    st.rerun()
            with col_val2:
                if st.button("🗑️ Supprimer tous", use_container_width=True, type="secondary"):
                    st.session_state.temp_joueurs = []
                    st.rerun()
        
        for idx, joueur in enumerate(st.session_state.temp_joueurs):
            col_j1, col_j2, col_j3, col_j4, col_j5 = st.columns([1, 2, 2, 2, 2])
            with col_j1:
                st.write(f"**{idx+1}**")
            with col_j2:
                st.write(joueur["Prénom"])
            with col_j3:
                st.write(joueur["Nom"])
            with col_j4:
                st.write(joueur["Catégorie"])
            with col_j5:
                if est_organisateur():
                    col_v, col_s = st.columns(2)
                    with col_v:
                        if st.button("✅", key=f"val_{idx}"):
                            st.session_state.joueurs.append(joueur)
                            st.session_state.temp_joueurs.pop(idx)
                            st.rerun()
                    with col_s:
                        if st.button("🗑️", key=f"sup_{idx}"):
                            st.session_state.temp_joueurs.pop(idx)
                            st.rerun()
    
    # Liste des joueurs validés
    st.subheader("📋 Joueurs inscrits")
    if st.session_state.joueurs:
        df_joueurs = pd.DataFrame(st.session_state.joueurs)
        st.dataframe(df_joueurs, use_container_width=True)
    else:
        st.info("Aucun joueur inscrit")
    
    # Import/Export
    if est_organisateur():
        st.divider()
        st.subheader("📥📤 Import/Export")
        
        col_imp, col_exp = st.columns(2)
        
        with col_imp:
            st.write("**Importer des joueurs**")
            fichier_import = st.file_uploader("Fichier CSV", type=['csv'], 
                                            help="Format: Prénom,Nom,Catégorie")
            if fichier_import and st.button("📥 Importer"):
                try:
                    df = pd.read_csv(fichier_import)
                    if all(col in df.columns for col in ['Prénom', 'Nom', 'Catégorie']):
                        nouveaux = 0
                        for _, row in df.iterrows():
                            if not joueur_existe(row['Prénom'], row['Nom']):
                                st.session_state.joueurs.append({
                                    "Prénom": row['Prénom'],
                                    "Nom": row['Nom'],
                                    "Catégorie": row['Catégorie']
                                })
                                nouveaux += 1
                        st.success(f"✅ {nouveaux} nouveaux joueurs importés!")
                        st.rerun()
                    else:
                        st.error("❌ Format CSV incorrect. Colonnes requises: Prénom,Nom,Catégorie")
                except Exception as e:
                    st.error(f"❌ Erreur: {e}")
        
        with col_exp:
            st.write("**Exporter les joueurs**")
            if st.session_state.joueurs:
                csv_data = pd.DataFrame(st.session_state.joueurs).to_csv(index=False).encode('utf-8')
                st.download_button("💾 Exporter CSV", csv_data, 
                                 f"joueurs_{st.session_state.nom_tournoi}.csv",
                                 "text/csv")

# Dans l'onglet "Joueurs" (après la section Import/Export):
with tabs[0]:
    # ... (code existant) ...
    
    # Ajouter la section Exportation après la section Import/Export
    if est_organisateur():
        st.divider()
        st.subheader("📤 Exportation complète des joueurs")
        
        col_exp1, col_exp2, col_exp3 = st.columns(3)
        
        with col_exp1:
            # Export PDF joueurs en attente
            if st.session_state.temp_joueurs:
                pdf_attente = exporter_joueurs_en_attente_pdf()
                st.download_button(
                    "📄 PDF Joueurs en attente",
                    pdf_attente,
                    f"joueurs_attente_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    "application/pdf",
                    use_container_width=True
                )
            else:
                st.button("📄 PDF Joueurs en attente", disabled=True, use_container_width=True)
        
        with col_exp2:
            # Export PDF joueurs validés
            if st.session_state.joueurs:
                pdf_valides = exporter_joueurs_valides_pdf()
                st.download_button(
                    "📄 PDF Joueurs validés",
                    pdf_valides,
                    f"joueurs_valides_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    "application/pdf",
                    use_container_width=True
                )
            else:
                st.button("📄 PDF Joueurs validés", disabled=True, use_container_width=True)
        
        with col_exp3:
            # Export Excel complet
            if st.session_state.joueurs or st.session_state.temp_joueurs:
                xlsx_complet = exporter_joueurs_complet_xlsx()
                st.download_button(
                    "📊 Excel Complet",
                    xlsx_complet,
                    f"joueurs_complet_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            else:
                st.button("📊 Excel Complet", disabled=True, use_container_width=True)
                
# Dans l'onglet ÉQUIPES (remplacement de la section actuelle)
with tabs[1]: 
    st.header("🤝 Gestion des Équipes")
    
    # Sélection du mode
    if st.session_state.mode_tournoi == "Classique":
        st.info("🏆 **Mode Classique**: Les équipes sont fixes tout au long du tournoi.")
        
        # Boutons de génération
        col_gen1, col_gen2 = st.columns(2)
        with col_gen1:
            if st.button("🎲 Générer nouvelles équipes", use_container_width=True, 
                        disabled=not est_organisateur()):
                generer_paires_equilibrees("nouveau")
                st.rerun()
        
        with col_gen2:
            joueurs_non_affectes = [j for j in st.session_state.joueurs 
                                   if get_nom_complet(j) not in 
                                   pd.concat([st.session_state.equipes_fixes['J1'], 
                                             st.session_state.equipes_fixes['J2']], 
                                            ignore_index=True).tolist()
                                   if "Joker" not in get_nom_complet(j)]
            
            if len(joueurs_non_affectes) >= 1:
                if st.button("➕ Ajouter des équipes", use_container_width=True,
                           disabled=not est_organisateur()):
                    generer_paires_equilibrees("ajouter")
                    st.rerun()
            else:
                st.button("➕ Ajouter des équipes", use_container_width=True, disabled=True,
                         help="Aucun joueur non affecté")
        
        # Affichage des équipes avec édition directe
        if not st.session_state.equipes_fixes.empty:
            st.subheader("Équipes fixes")
            
            if est_organisateur():
                # Créer une copie du DataFrame pour l'édition
                df_display = st.session_state.equipes_fixes.copy()
                
                # Configurer l'éditeur de données
                edited_df = st.data_editor(
                    df_display,
                    use_container_width=True,
                    column_config={
                        "ID": st.column_config.TextColumn("ID", disabled=True),
                        "Surnom": st.column_config.TextColumn(
                            "Surnom",
                            help="Modifiez le surnom de l'équipe",
                            required=False
                        ),
                        "J1": st.column_config.TextColumn("Joueur 1", disabled=True),
                        "Cat1": st.column_config.TextColumn("Cat1", disabled=True),
                        "J2": st.column_config.TextColumn("Joueur 2", disabled=True),
                        "Cat2": st.column_config.TextColumn("Cat2", disabled=True),
                        "Coeff": st.column_config.NumberColumn("Coeff", disabled=True, format="%.3f"),
                    },
                    hide_index=True,
                    key="edit_equipes_table"
                )
                
                # Bouton pour appliquer les modifications
                if st.button("💾 Enregistrer les modifications", use_container_width=True, type="primary"):
                    # Vérifier les doublons de surnoms
                    surnoms_uniques = {}
                    doublons_trouves = False
                    
                    for idx, row in edited_df.iterrows():
                        surnom = str(row['Surnom']).strip()
                        if surnom and surnom != "nan":
                            if surnom in surnoms_uniques:
                                st.error(f"❌ Le surnom '{surnom}' est utilisé par plusieurs équipes!")
                                doublons_trouves = True
                                break
                            surnoms_uniques[surnom] = row['ID']
                    
                    if not doublons_trouves:
                        # Appliquer les modifications
                        for idx, row in edited_df.iterrows():
                            equipe_id = row['ID']
                            nouveau_surnom = str(row['Surnom']).strip()
                            
                            # Mettre à jour dans le DataFrame original
                            mask = st.session_state.equipes_fixes['ID'] == equipe_id
                            if mask.any():
                                if nouveau_surnom and nouveau_surnom != "nan":
                                    st.session_state.equipes_fixes.loc[mask, 'Surnom'] = nouveau_surnom
                                else:
                                    # Si le surnom est vide, remettre l'ID par défaut
                                    st.session_state.equipes_fixes.loc[mask, 'Surnom'] = equipe_id
                        
                        st.success("✅ Modifications enregistrées!")
                        st.rerun()
                
                # Section suppression
                st.subheader("🗑️ Suppression d'équipes")
                
                # Créer une liste pour la sélection
                options_suppression = {}
                for idx, eq in st.session_state.equipes_fixes.iterrows():
                    nom_affichage = get_nom_affichage_equipe(eq)
                    options_suppression[f"{eq['ID']}"] = f"{nom_affichage} ({eq['J1']} & {eq['J2']})"
                
                if options_suppression:
                    equipes_a_supprimer = st.multiselect(
                        "Sélectionnez les équipes à supprimer:",
                        options=list(options_suppression.keys()),
                        format_func=lambda x: options_suppression[x]
                    )
                    
                    if equipes_a_supprimer and st.button("🗑️ Supprimer les équipes sélectionnées", type="secondary"):
                        # Vérifier si les équipes sont dans des matchs
                        equipes_dans_matchs = []
                        for equipe_id in equipes_a_supprimer:
                            if not st.session_state.matchs.empty:
                                est_dans_match = any(
                                    (st.session_state.matchs['Equipe A'] == equipe_id) |
                                    (st.session_state.matchs['Equipe B'] == equipe_id)
                                )
                                if est_dans_match:
                                    equipes_dans_matchs.append(equipe_id)
                        
                        if equipes_dans_matchs:
                            st.error(f"❌ Impossible de supprimer: {', '.join(equipes_dans_matchs)} - déjà dans un match")
                        else:
                            # Supprimer les équipes
                            st.session_state.equipes_fixes = st.session_state.equipes_fixes[
                                ~st.session_state.equipes_fixes['ID'].isin(equipes_a_supprimer)
                            ]
                            st.success(f"✅ {len(equipes_a_supprimer)} équipe(s) supprimée(s)!")
                            st.rerun()
                else:
                    st.info("Aucune équipe à supprimer")
            
            else:
                # Mode joueur : affichage simple
                df_display = st.session_state.equipes_fixes.copy()
                df_display['Affichage'] = df_display.apply(
                    lambda row: f"{get_nom_affichage_equipe(row)} ({row['J1']} & {row['J2']})", 
                    axis=1
                )
                st.dataframe(df_display[['Affichage', 'Cat1', 'Cat2', 'Coeff']], 
                           use_container_width=True, hide_index=True)
        
        else:
            st.info("Aucune équipe créée. Générez des équipes pour commencer.")
    
    else:  # Mode Individuel
        st.info("🎯 **Mode Individuel**: Les équipes sont regénérées à chaque round.")
        
        # Affichage des équipes du dernier round
        equipes_actuelles = get_equipes_actuelles()
        if not equipes_actuelles.empty:
            st.subheader(f"Équipes du Round {get_current_round()}")
            
            # Pour le mode individuel, on peut aussi permettre de modifier les surnoms
            if est_organisateur():
                df_display = equipes_actuelles.copy()
                
                edited_df = st.data_editor(
                    df_display,
                    use_container_width=True,
                    column_config={
                        "ID": st.column_config.TextColumn("ID", disabled=True),
                        "Surnom": st.column_config.TextColumn(
                            "Surnom",
                            help="Modifiez le surnom de l'équipe",
                            required=False
                        ),
                        "J1": st.column_config.TextColumn("Joueur 1", disabled=True),
                        "Cat1": st.column_config.TextColumn("Cat1", disabled=True),
                        "J2": st.column_config.TextColumn("Joueur 2", disabled=True),
                        "Cat2": st.column_config.TextColumn("Cat2", disabled=True),
                        "Coeff": st.column_config.NumberColumn("Coeff", disabled=True, format="%.3f"),
                    },
                    hide_index=True,
                    key="edit_equipes_individuel_table"
                )
                
                # Bouton pour appliquer les modifications
                if st.button("💾 Enregistrer les modifications", use_container_width=True, type="primary"):
                    # Mettre à jour dans l'historique
                    round_actuel = get_current_round()
                    for idx, row in edited_df.iterrows():
                        equipe_id = row['ID']
                        nouveau_surnom = str(row['Surnom']).strip()
                        
                        # Mettre à jour dans l'historique
                        mask = (st.session_state.historique_equipes['Round'] == round_actuel) & \
                               (st.session_state.historique_equipes['ID'] == equipe_id)
                        
                        if mask.any():
                            if nouveau_surnom and nouveau_surnom != "nan":
                                st.session_state.historique_equipes.loc[mask, 'Surnom'] = nouveau_surnom
                            else:
                                st.session_state.historique_equipes.loc[mask, 'Surnom'] = equipe_id
                    
                    st.success("✅ Modifications enregistrées!")
                    st.rerun()
            else:
                st.dataframe(equipes_actuelles, use_container_width=True, hide_index=True)
            
            # Historique des équipes
            with st.expander("📜 Historique des équipes par round"):
                if not st.session_state.historique_equipes.empty:
                    for round_num in sorted(st.session_state.historique_equipes["Round"].unique()):
                        st.write(f"**Round {round_num}**")
                        df_round = st.session_state.historique_equipes[
                            st.session_state.historique_equipes["Round"] == round_num
                        ].drop(columns=["Round"])
                        st.dataframe(df_round, use_container_width=True, hide_index=True)
        else:
            st.info("💡 Aucun round n'a encore été généré. Créez un premier round dans l'onglet Matchs.")
    
    # SECTION EXPORTATION (garder cette partie inchangée)
    if est_organisateur():
        st.divider()
        st.subheader("📤 Exportation des données d'équipes")
        
        col_exp_eq1, col_exp_eq2, col_exp_eq3 = st.columns(3)
        
        with col_exp_eq1:
            # Export PDF équipes actuelles
            equipes_actuelles = get_equipes_actuelles()
            if not equipes_actuelles.empty:
                pdf_equipes = exporter_equipes_actuelles_pdf()
                st.download_button(
                    "📄 PDF Équipes actuelles",
                    pdf_equipes,
                    f"equipes_actuelles_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    "application/pdf",
                    use_container_width=True
                )
            else:
                st.button("📄 PDF Équipes actuelles", disabled=True, use_container_width=True)
        
        with col_exp_eq2:
            # Export PDF historique (mode individuel)
            if st.session_state.mode_tournoi == "Individuel" and not st.session_state.historique_equipes.empty:
                pdf_historique = exporter_historique_equipes_pdf()
                st.download_button(
                    "📄 PDF Historique équipes",
                    pdf_historique,
                    f"historique_equipes_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    "application/pdf",
                    use_container_width=True
                )
            else:
                st.button("📄 PDF Historique équipes", disabled=True, 
                         help="Disponible uniquement en mode Individuel avec historique", 
                         use_container_width=True)
        
        with col_exp_eq3:
            # Export Excel complet
            equipes_actuelles = get_equipes_actuelles()
            if not equipes_actuelles.empty or not st.session_state.historique_equipes.empty or not st.session_state.equipes_fixes.empty:
                xlsx_equipes = exporter_equipes_complet_xlsx()
                st.download_button(
                    "📊 Excel Complet équipes",
                    xlsx_equipes,
                    f"equipes_complet_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            else:
                st.button("📊 Excel Complet équipes", disabled=True, use_container_width=True)
                
# Onglet 3: Matchs
with tabs[2]:
    st.header("🏸 Gestion des Matchs")
    
    # Boutons de génération
    col_btn1, col_btn2, col_btn3 = st.columns(3)
    
    with col_btn1:
        disabled = not est_organisateur()
        
        if st.session_state.mode_tournoi == "Classique":
            if st.session_state.equipes_fixes.empty or len(st.session_state.equipes_fixes) < 2:
                disabled = True
                st.caption("⚠️ Besoin d'au moins 2 équipes")
        else:
            if len(st.session_state.joueurs) < 2:
                disabled = True
                st.caption("⚠️ Besoin d'au moins 2 joueurs")
        
        if st.button("🎲 Nouveau Round", use_container_width=True, disabled=disabled):
            generer_round()
            st.rerun()
    
    with col_btn2:
        if st.session_state.mode_tournoi == "Individuel" and est_organisateur():
            if st.button("🔚 Générer derniers rounds", use_container_width=True,
                        type="secondary", help="Génère les rounds nécessaires pour équilibrer les matchs joués"):
                generer_derniers_rounds()
                st.rerun()
        else:
            st.button("🔚 Générer derniers rounds", use_container_width=True, disabled=True,
                     help="Disponible uniquement en mode Individuel")
    
    with col_btn3:
        if not st.session_state.matchs.empty and est_organisateur():
            if st.session_state.get("show_popup_matchs_simple", False):
                st.warning("⚠️ ATTENTION : Réinitialisation des matchs")
                st.error("Cette action va supprimer TOUS les matchs joués. Les équipes et joueurs seront conservés.")
            
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✅ Oui, réinitialiser les matchs", use_container_width=True, type="primary"):
                        reinitialiser_matchs_simple_avec_confirmation()
                        st.rerun()
                with col2:
                    if st.button("❌ Annuler", use_container_width=True):
                        st.session_state["show_popup_matchs_simple"] = False
                        st.rerun()
            else:
                if st.button("🔄 Réinitialiser matchs", use_container_width=True, type="secondary"):
                    st.session_state["show_popup_matchs_simple"] = True
                    st.rerun()
    
    # Informations sur le round actuel
    st.write(f"**Round actuel:** {get_current_round()}")
    
    # Affichage des matchs
    if not st.session_state.matchs.empty:
        st.subheader("📋 Matchs en cours")
        
        # Créer une copie pour l'affichage
        matchs_display = st.session_state.matchs_detail.copy()
        
        # Ajouter les surnoms des équipes
        for idx, match in matchs_display.iterrows():
            # Équipe A
            if st.session_state.mode_tournoi == "Classique":
                eq_a = st.session_state.equipes_fixes[
                    st.session_state.equipes_fixes["ID"] == match["Equipe_A_ID"]
                ]
                if not eq_a.empty:
                    matchs_display.at[idx, "Equipe_A_Display"] = get_nom_affichage_equipe(eq_a.iloc[0])
                else:
                    matchs_display.at[idx, "Equipe_A_Display"] = match["Equipe_A_ID"]
            else:
                # Mode Individuel
                round_num = match["Round"]
                equipes_round = get_equipes_par_round(round_num)
                if not equipes_round.empty:
                    eq_a = equipes_round[equipes_round["ID"] == match["Equipe_A_ID"]]
                    if not eq_a.empty:
                        matchs_display.at[idx, "Equipe_A_Display"] = get_nom_affichage_equipe(eq_a.iloc[0])
                    else:
                        matchs_display.at[idx, "Equipe_A_Display"] = match["Equipe_A_ID"]
                else:
                    matchs_display.at[idx, "Equipe_A_Display"] = match["Equipe_A_ID"]
            
            # Équipe B
            if st.session_state.mode_tournoi == "Classique":
                eq_b = st.session_state.equipes_fixes[
                    st.session_state.equipes_fixes["ID"] == match["Equipe_B_ID"]
                ]
                if not eq_b.empty:
                    matchs_display.at[idx, "Equipe_B_Display"] = get_nom_affichage_equipe(eq_b.iloc[0])
                else:
                    matchs_display.at[idx, "Equipe_B_Display"] = match["Equipe_B_ID"]
            else:
                # Mode Individuel
                round_num = match["Round"]
                equipes_round = get_equipes_par_round(round_num)
                if not equipes_round.empty:
                    eq_b = equipes_round[equipes_round["ID"] == match["Equipe_B_ID"]]
                    if not eq_b.empty:
                        matchs_display.at[idx, "Equipe_B_Display"] = get_nom_affichage_equipe(eq_b.iloc[0])
                    else:
                        matchs_display.at[idx, "Equipe_B_Display"] = match["Equipe_B_ID"]
                else:
                    matchs_display.at[idx, "Equipe_B_Display"] = match["Equipe_B_ID"]
        
        # Sélectionner les colonnes à afficher
        display_cols = ["Round", "Terrain", "Type", "Equipe_A_Display", "J1_A", "J2_A", 
                       "Score_A", "Score_B", "Equipe_B_Display", "J1_B", "J2_B"]
        
        if "Jokers" in matchs_display.columns:
            display_cols.append("Jokers")
        
        matchs_display = matchs_display[display_cols]
        matchs_display = matchs_display.rename(columns={
            "Equipe_A_Display": "Équipe A",
            "Equipe_B_Display": "Équipe B",
            "Score_A": "Score A",
            "Score_B": "Score B"
        })
        
        # Éditeur de scores - VERSION CORRIGÉE
        if est_organisateur():
            # Créer une copie pour éviter les modifications directes
            display_df = matchs_display.copy()
            
            # Utiliser un formulaire pour regrouper les modifications
            with st.form("scores_form"):
                edited_df = st.data_editor(
                    display_df,
                    use_container_width=True,
                    column_config={
                        "Round": st.column_config.NumberColumn("Round", disabled=True),
                        "Terrain": st.column_config.TextColumn("Terrain", disabled=True),
                        "Type": st.column_config.TextColumn("Type", disabled=True),
                        "Équipe A": st.column_config.TextColumn("Équipe A", disabled=True),
                        "J1_A": st.column_config.TextColumn("J1 A", disabled=True),
                        "J2_A": st.column_config.TextColumn("J2 A", disabled=True),
                        "Score A": st.column_config.NumberColumn(
                            "Score A", 
                            min_value=0, 
                            max_value=100,
                            step=1,
                            required=True
                        ),
                        "Score B": st.column_config.NumberColumn(
                            "Score B", 
                            min_value=0, 
                            max_value=100,
                            step=1,
                            required=True
                        ),
                        "Équipe B": st.column_config.TextColumn("Équipe B", disabled=True),
                        "J1_B": st.column_config.TextColumn("J1 B", disabled=True),
                        "J2_B": st.column_config.TextColumn("J2 B", disabled=True),
                        "Jokers": st.column_config.TextColumn("Jokers", disabled=True)
                    },
                    hide_index=True,
                    # Clé basée sur un hash des données pour éviter les conflits
                    key=f"matchs_editor_{hash(str(matchs_display.values.tobytes()))}"
                )
                
                submitted = st.form_submit_button("💾 Enregistrer les scores", use_container_width=True)
                
                if submitted:
                    # Mettre à jour les scores dans session_state
                    for idx, row in edited_df.iterrows():
                        # Trouver l'index correspondant dans matchs_detail
                        detail_idx = st.session_state.matchs_detail[
                            (st.session_state.matchs_detail["Round"] == row["Round"]) &
                            (st.session_state.matchs_detail["Terrain"] == row["Terrain"])
                        ].index
                        
                        if len(detail_idx) > 0:
                            detail_idx = detail_idx[0]
                            st.session_state.matchs_detail.at[detail_idx, "Score_A"] = row["Score A"]
                            st.session_state.matchs_detail.at[detail_idx, "Score_B"] = row["Score B"]
                            
                            # Mettre à jour les matchs simplifiés
                            match_idx = st.session_state.matchs[
                                (st.session_state.matchs["Round"] == row["Round"]) &
                                (st.session_state.matchs["Terrain"] == row["Terrain"])
                            ].index
                            
                            if len(match_idx) > 0:
                                st.session_state.matchs.at[match_idx[0], "Score A"] = row["Score A"]
                                st.session_state.matchs.at[match_idx[0], "Score B"] = row["Score B"]
                    
                    st.success("✅ Scores enregistrés!")
                    st.rerun()
        else:
            # Mode joueur - affichage simple
            st.dataframe(matchs_display, use_container_width=True, hide_index=True)
    else:
        st.info("Aucun match programmé. Générez un premier round!")

    # Ajouter la section Exportation
    if not st.session_state.matchs_detail.empty:
        st.divider()
        st.subheader("📤 Exportation des matchs")
        
        col_exp_m1, col_exp_m2, col_exp_m3 = st.columns(3)
        
        with col_exp_m1:
            # Export PDF matchs en cours
            pdf_en_cours = exporter_matchs_en_cours_pdf()
            st.download_button(
                "📄 PDF Matchs en cours",
                pdf_en_cours,
                f"matchs_en_cours_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                "application/pdf",
                use_container_width=True
            )
        
        with col_exp_m2:
            # Export PDF tous les matchs
            pdf_tous = exporter_tous_matchs_pdf()
            st.download_button(
                "📄 PDF Tous les matchs",
                pdf_tous,
                f"matchs_tous_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                "application/pdf",
                use_container_width=True
            )
        
        with col_exp_m3:
            # Export Excel complet
            xlsx_matchs = exporter_matchs_complet_xlsx()
            st.download_button(
                "📊 Excel Complet matchs",
                xlsx_matchs,
                f"matchs_complet_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
# Onglet 4: Statistiques
with tabs[3]:
    st.header("📊 Statistiques du Tournoi")
    
    if st.session_state.mode_tournoi == "Individuel":
        st.info("🎯 **Mode Individuel**: Statistiques d'équilibre des matchs joués")
        
        # Statistiques d'équilibre
        st.subheader("⚖️ Équilibre des matchs joués")
        df_stats = afficher_statistiques_equilibre()
        
        if df_stats is not None and not df_stats.empty:
            st.dataframe(df_stats, use_container_width=True)
            
            # Graphique de distribution
            st.subheader("📈 Distribution des matchs joués")
            chart_data = df_stats.set_index("Joueur")["Matchs Joués"]
            st.bar_chart(chart_data)
            
            # Analyse des retards
            joueurs_en_retard, max_matchs, retards = analyser_retards_joueurs()
            
            if joueurs_en_retard:
                st.warning(f"⚠️ {len(joueurs_en_retard)} joueur(s) ont un retard")
                
                col_ret1, col_ret2 = st.columns(2)
                with col_ret1:
                    st.write("**Joueurs les plus en retard:**")
                    for joueur in joueurs_en_retard[:5]:
                        st.write(f"- {joueur}: {retards[joueur]['matchs']} matchs (retard: {retards[joueur]['retard']})")
                
                with col_ret2:
                    st.write("**Recommandations:**")
                    if len(joueurs_en_retard) > 0:
                        rounds_needed = max(retards[j]['retard'] for j in joueurs_en_retard)
                        st.write(f"- {rounds_needed} round(s) de rattrapage nécessaire(s)")
                        st.write(f"- {len(joueurs_en_retard)} joueur(s) à rattraper")
            else:
                st.success("✅ Tous les joueurs ont le même nombre de matchs!")
    
    # Statistiques générales
    st.subheader("📊 Statistiques générales")
    
    col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
    
    with col_stat1:
        st.metric("Joueurs inscrits", len(st.session_state.joueurs))
    
    with col_stat2:
        if st.session_state.mode_tournoi == "Classique":
            if not st.session_state.equipes_fixes.empty:
                st.metric("Équipes", len(st.session_state.equipes_fixes))
            else:
                st.metric("Équipes", 0)
        else:
            equipes_actuelles = get_equipes_actuelles()
            if not equipes_actuelles.empty:
                st.metric("Équipes actuelles", len(equipes_actuelles))
            else:
                st.metric("Équipes actuelles", 0)
    
    with col_stat3:
        if not st.session_state.matchs.empty:
            st.metric("Matchs joués", len(st.session_state.matchs))
        else:
            st.metric("Matchs joués", 0)
    
    with col_stat4:
        st.metric("Rounds joués", get_current_round())

 # Ajouter la section Exportation
    if est_organisateur():
        st.divider()
        st.subheader("📤 Exportation des statistiques")
        
        col_exp_s1, col_exp_s2 = st.columns(2)
        
        with col_exp_s1:
            # Export PDF statistiques
            pdf_stats = exporter_statistiques_pdf()
            st.download_button(
                "📄 PDF Statistiques",
                pdf_stats,
                f"statistiques_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                "application/pdf",
                use_container_width=True
            )
        
        with col_exp_s2:
            # Export Excel statistiques
            xlsx_stats = exporter_statistiques_xlsx()
            st.download_button(
                "📊 Excel Statistiques",
                xlsx_stats,
                f"statistiques_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

# Onglet 5: Classements
with tabs[4]:
    st.header("🏆 Classements")
    
    # Sélection du type de classement
    if st.session_state.mode_tournoi == "Classique":
        tab_classement = st.selectbox("Type de classement", 
                                     ["Classement par équipes", "Classement individuel"])
    else:
        tab_classement = "Classement individuel"
        st.info("🎯 **Mode Individuel**: Seul le classement individuel a du sens")
    
    if tab_classement == "Classement par équipes" and st.session_state.mode_tournoi == "Classique":
        st.subheader("🏆 Classement par équipes")
        
        if not st.session_state.matchs.empty and not st.session_state.equipes_fixes.empty:
            # Calculer le classement
            stats = []
            for _, eq in st.session_state.equipes_fixes.iterrows():
                eid = eq["ID"]
                m_eq = st.session_state.matchs[
                    (st.session_state.matchs["Equipe A"] == eid) | 
                    (st.session_state.matchs["Equipe B"] == eid)
                ]
                
                pm, pe, v, n, d = 0, 0, 0, 0, 0
                for _, m in m_eq.iterrows():
                    if m["Score A"] == 0 and m["Score B"] == 0:
                        continue
                    
                    is_a = m["Equipe A"] == eid
                    ma, sa = (m["Score A"], m["Score B"]) if is_a else (m["Score B"], m["Score A"])
                    
                    pm += ma
                    pe += sa
                    
                    if ma > sa:
                        v += 1
                    elif ma == sa:
                        n += 1
                    else:
                        d += 1
                
                diff = pm - pe
                if st.session_state.algo_classement == "Pondéré":
                    score = round(((v * 3) + (n * 1)) * eq["Coeff"], 2)
                else:
                    score = (v * 2) + (n * 1)
                
                stats.append({
                    "Équipe": get_nom_affichage_equipe(eq),
                    "Joueurs": f"{eq['J1']} & {eq['J2']}",
                    "V": v, "N": n, "D": d,
                    "PM": pm, "PE": pe, "Diff": diff,
                    "Points": score
                })
            
            if stats:
                df_classement = pd.DataFrame(stats).sort_values(by=["Points", "Diff"], ascending=False)
                df_classement.index = range(1, len(df_classement) + 1)
                df_classement.index.name = "Rang"
                
                st.dataframe(df_classement, use_container_width=True)
            else:
                st.info("Aucune statistique disponible")
        else:
            st.info("Aucun match joué pour le moment")
    
    else:  # Classement individuel
        st.subheader("👤 Classement individuel")
        
        df_classement = calculer_classement_individuel_avec_jokers()
        
        if df_classement.empty:
            st.info("Aucun match joué pour le moment")
 # Ajouter la section Exportation après les classements
    if est_organisateur():
        st.divider()
        st.subheader("📤 Exportation des classements")
        
        col_exp_c1, col_exp_c2, col_exp_c3 = st.columns(3)
        
        with col_exp_c1:
            # Export PDF classement équipes (mode classique)
            #if st.session_state.mode_tournoi == "Classique":
            if st.session_state.mode_tournoi == "Classique" and not st.session_state.matchs.empty:
                pdf_class_eq = exporter_classement_equipes_pdf()
                st.download_button(
                    "📄 PDF Classement équipes",
                    pdf_class_eq,
                    f"classement_equipes_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    "application/pdf",
                    use_container_width=True
                )
            else:
                st.button("📄 PDF Classement équipes", disabled=True,
                         help="Disponible uniquement en mode Classique",
                         use_container_width=True)
        
        with col_exp_c2:
            # Export PDF classement individuel
            df_classement = calculer_classement_individuel_avec_jokers()
            if not df_classement.empty:
                pdf_class_indiv = exporter_classement_individuel_pdf()
                st.download_button(
                    "📄 PDF Classement individuel",
                    pdf_class_indiv,
                    f"classement_individuel_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    "application/pdf",
                    use_container_width=True
                )
            else:
                st.button("📄 PDF Classement individuel", disabled=True,
                         help="Aucun match joué pour le moment",
                         use_container_width=True)
        
        with col_exp_c3:
            # Export Excel complet des classements
            df_classement = calculer_classement_individuel_avec_jokers()
            if not df_classement.empty or (st.session_state.mode_tournoi == "Classique" and not st.session_state.matchs.empty):
                xlsx_class = exporter_classements_complet_xlsx()
                st.download_button(
                    "📊 Excel Complet classements",
                    xlsx_class,
                    f"classements_complet_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            else:
                st.button("📊 Excel Complet classements", disabled=True,
                         help="Aucun classement disponible",
                         use_container_width=True)

# Onglet 6: Paramètres
with tabs[5]:
    if not est_organisateur():
        st.warning("🔒 Cette section est réservée à l'organisateur")
    else:
        st.header("⚙️ Paramètres du Tournoi")
        
        # Configuration de base
        st.subheader("📝 Configuration générale")
        
        col_conf1, col_conf2 = st.columns(2)
        
        with col_conf1:
            nouveau_nom = st.text_input("Nom du tournoi", st.session_state.nom_tournoi)
            if nouveau_nom != st.session_state.nom_tournoi:
                st.session_state.nom_tournoi = nouveau_nom
                st.rerun()
        
        with col_conf2:
            st.session_state.nb_terrains = st.number_input("Nombre de terrains", 
                                                          min_value=1, max_value=20,
                                                          value=st.session_state.nb_terrains)
        
        # Mode du tournoi
        st.subheader("🎮 Mode du tournoi")
        
        mode = st.radio(
            "Sélectionnez le mode de tournoi:",
            ["Classique", "Individuel"],
            index=0 if st.session_state.mode_tournoi == "Classique" else 1,
            help="Classique: Équipes fixes, classement par équipe. Individuel: Équipes variables, priorité aux moins actifs."
        )
        
        if mode != st.session_state.mode_tournoi:
            st.session_state.mode_tournoi = mode
            if mode == "Individuel":
                st.warning("⚠️ Passage en mode Individuel: Les équipes seront regénérées à chaque round avec priorité aux joueurs ayant le moins joué.")
            st.rerun()
        
        # Méthodes de classement
        st.subheader("📊 Méthodes de classement")
        
        col_algo1, col_algo2 = st.columns(2)
        
        with col_algo1:
            st.session_state.algo_classement = st.radio(
                "Classement par équipes:",
                ["Pondéré", "Standard"],
                index=0 if st.session_state.algo_classement == "Pondéré" else 1
            )
        
        with col_algo2:
            st.session_state.algo_classement_individuel = st.radio(
                "Classement individuel:",
                ["Pondéré", "Standard"],
                index=0 if st.session_state.algo_classement_individuel == "Pondéré" else 1
            )
        
        # Catégories et coefficients
        st.subheader("🏷️ Catégories et coefficients")
        
        for categorie, coeff in list(st.session_state.categories_dict.items()):
            if categorie == "Joker":
                continue
            
            col_cat1, col_cat2, col_cat3 = st.columns([3, 2, 1])
            
            with col_cat1:
                st.write(f"**{categorie}**")
            
            with col_cat2:
                nouveau_coeff = st.number_input(
                    f"Coefficient {categorie}",
                    min_value=0.5,
                    max_value=2.0,
                    value=coeff,
                    step=0.05,
                    key=f"coeff_{categorie}"
                )
                if nouveau_coeff != coeff:
                    st.session_state.categories_dict[categorie] = nouveau_coeff
            
            with col_cat3:
                if st.button("🗑️", key=f"del_{categorie}"):
                    del st.session_state.categories_dict[categorie]
                    st.rerun()
        
        # Ajouter une nouvelle catégorie
        with st.expander("➕ Ajouter une nouvelle catégorie"):
            col_new1, col_new2 = st.columns(2)
            
            with col_new1:
                nouvelle_cat = st.text_input("Nom de la catégorie")
            
            with col_new2:
                nouveau_coeff = st.number_input("Coefficient", min_value=0.5, max_value=2.0, value=1.0, step=0.05)
            
            if st.button("Ajouter la catégorie") and nouvelle_cat:
                st.session_state.categories_dict[nouvelle_cat] = nouveau_coeff
                st.success(f"✅ Catégorie '{nouvelle_cat}' ajoutée!")
                st.rerun()
        
        # Image de fond
        st.subheader("🖼️ Personnalisation")
        
        image_fond = st.file_uploader("Image de fond", type=['jpg', 'jpeg', 'png'])
        if image_fond:
            st.session_state.bg_image_data = image_fond
            st.success("✅ Image de fond mise à jour!")
            st.rerun()
        
        if st.session_state.bg_image_data:
            if st.button("🗑️ Supprimer l'image de fond"):
                st.session_state.bg_image_data = None
                st.rerun()
        
        # Réinitialisation
         # SECTION RÉINITIALISATION DES MATCHS & CLASSEMENT
        st.divider()
        st.subheader("🔄 Réinitialisation des Matchs & Classement")
        
        if st.session_state.get("show_popup_matchs", False):
            st.warning("⚠️ ATTENTION : Réinitialisation complète")
            st.error("Cette action va supprimer TOUS les matchs joués, le classement, et l'historique des équipes. Les joueurs et équipes fixes seront conservés.")
            
            # Statistiques
            if not st.session_state.matchs.empty:
                st.info(f"""
                **Données qui seront supprimées :**
                - {len(st.session_state.matchs)} match(s)
                - {len(st.session_state.matchs_detail)} match(s) détaillé(s)
                - {len(st.session_state.historique_equipes)} équipe(s) dans l'historique
                - {get_current_round()} round(s) de jeu
                """)
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Oui, tout réinitialiser", use_container_width=True, type="primary"):
                    reinitialiser_matchs_avec_confirmation()
                    st.rerun()
            with col2:
                if st.button("❌ Annuler", use_container_width=True):
                    st.session_state["show_popup_matchs"] = False
                    st.rerun()
        else:
            if st.button("🔄 Réinitialiser les Matchs & Classement", use_container_width=True, 
                        type="secondary", help="Supprime tous les matchs et l'historique des équipes"):
                st.session_state["show_popup_matchs"] = True
                st.rerun()
        
        # SECTION RÉINITIALISATION COMPLÈTE
        st.divider()
        st.subheader("💣 Réinitialisation complète du tournoi")
        
        if st.session_state.get("show_popup_tournoi", False):
            st.error("🚨 DANGER : Réinitialisation complète du tournoi")
            st.error("Cette action va supprimer TOUTES les données du tournoi :")
            st.error("- Tous les joueurs (validés et en attente)")
            st.error("- Toutes les équipes (fixes et historiques)")
            st.error("- Tous les matchs et classements")
            st.error("- Tous les paramètres (sauf profil)")
            
            # Statistiques détaillées
            stats = []
            if st.session_state.joueurs:
                stats.append(f"- {len(st.session_state.joueurs)} joueur(s) validé(s)")
            if st.session_state.temp_joueurs:
                stats.append(f"- {len(st.session_state.temp_joueurs)} joueur(s) en attente")
            if not st.session_state.equipes_fixes.empty:
                stats.append(f"- {len(st.session_state.equipes_fixes)} équipe(s) fixe(s)")
            if not st.session_state.matchs.empty:
                stats.append(f"- {len(st.session_state.matchs)} match(s)")
            if not st.session_state.historique_equipes.empty:
                stats.append(f"- {len(st.session_state.historique_equipes)} équipe(s) dans l'historique")
            
            if stats:
                st.warning("**Résumé des données à supprimer :**")
                for stat in stats:
                    st.write(stat)
            
            # Double confirmation
            st.warning("⚠️ Cette action est IRRÉVERSIBLE !")
            
            # Deuxième niveau de confirmation
            confirmation_text = st.text_input(
                "Pour confirmer, tapez 'SUPPRIMER TOUT' :",
                key="confirm_delete_all"
            )
            
            col1, col2 = st.columns(2)
            with col1:
                confirm_disabled = confirmation_text != "SUPPRIMER TOUT"
                if st.button("✅ Oui, tout supprimer", 
                           use_container_width=True, 
                           type="primary",
                           disabled=confirm_disabled,
                           help="Tapez 'SUPPRIMER TOUT' pour activer ce bouton"):
                    reinitialiser_tournoi_avec_confirmation()
                    st.rerun()
            with col2:
                if st.button("❌ Annuler", use_container_width=True):
                    st.session_state["show_popup_tournoi"] = False
                    st.rerun()
        else:
            if st.button("💣 RÉINITIALISER TOUT LE TOURNOI", 
                        use_container_width=True, 
                        type="primary",
                        help="Supprime ABSOLUMENT TOUTES les données du tournoi"):
                st.session_state["show_popup_tournoi"] = True
                st.rerun()


# Pied de page
st.divider()
st.caption(f"Duck Manager Pro v2.0 • Mode: {st.session_state.mode_tournoi} • {datetime.now().strftime('%d/%m/%Y %H:%M')}")