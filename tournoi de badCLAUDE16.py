import streamlit as st
import pandas as pd
import random
import base64

# --- 1. INITIALISATION DES VARIABLES DE SESSION ---
if 'categories_dict' not in st.session_state:
    st.session_state.categories_dict = {"Bien-être": 1.2, "Compétiteur": 1.05, "Très Bon": 1.0}
if 'nom_tournoi' not in st.session_state:
    st.session_state.nom_tournoi = "CBAB Duck's Manager Pro"
if 'joueurs' not in st.session_state:
    st.session_state.joueurs = []
if 'equipes' not in st.session_state:
    st.session_state.equipes = pd.DataFrame(columns=["ID", "J1", "Cat1", "J2", "Cat2", "Coeff"])
if 'erreur_saisie' not in st.session_state:
    st.session_state.erreur_saisie = None
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

# Configuration de la page avec le nom dynamique
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

# --- 3. LOGIQUE MÉTIER ---

def generer_paires_equilibrees(mode="nouveau"):
    """
    mode="nouveau" : régénère toutes les équipes
    mode="ajouter" : ajoute uniquement les joueurs non affectés
    """
    if mode == "nouveau":
        # Mode original : tous les joueurs
        joueurs_a_traiter = [j for j in st.session_state.joueurs 
                            if j['Prénom'].strip() != "" and j['Nom'].strip() != ""]
    else:
        # Mode ajout : uniquement les joueurs non affectés
        joueurs_a_traiter = [j for j in st.session_state.joueurs 
                            if j['Prénom'].strip() != "" and j['Nom'].strip() != "" 
                            and not joueur_dans_equipe(j['Prénom'], j['Nom'])]
    
    if len(joueurs_a_traiter) < 2:
        st.error("Il faut au moins 2 joueurs non affectés." if mode == "ajouter" else "Il faut au moins 2 joueurs valides.")
        return
    
    if len(joueurs_a_traiter) % 2 == 1:
        joueur_exclu = random.choice(joueurs_a_traiter)
        st.warning(f"⚠️ Nombre impair : {get_nom_complet(joueur_exclu)} ne jouera pas ce tour.")
        joueurs_a_traiter = [j for j in joueurs_a_traiter 
                            if not (j['Prénom'] == joueur_exclu['Prénom'] and j['Nom'] == joueur_exclu['Nom'])]
    
    # Tri par coefficient (niveau)
    joueurs_tries = sorted(joueurs_a_traiter, 
                          key=lambda x: st.session_state.categories_dict[x['Catégorie']], 
                          reverse=True)
    
    paires = []
    while len(joueurs_tries) >= 2:
        paires.append((joueurs_tries.pop(0), joueurs_tries.pop(-1)))
    
    # Calculer l'ID de départ pour les nouvelles équipes
    if mode == "ajouter" and not st.session_state.equipes.empty:
        dernier_id = max([int(eq.replace("Équipe ", "")) for eq in st.session_state.equipes["ID"]])
        start_id = dernier_id + 1
    else:
        start_id = 1
        if mode == "nouveau":
            st.session_state.equipes = pd.DataFrame(columns=["ID", "J1", "Cat1", "J2", "Cat2", "Coeff"])
    
    new_teams = []
    for i, (p1, p2) in enumerate(paires, start_id):
        c1, c2 = p1['Catégorie'], p2['Catégorie']
        avg_coeff = (st.session_state.categories_dict[c1] + st.session_state.categories_dict[c2]) / 2
        new_teams.append({
            "ID": f"Équipe {i}", 
            "J1": get_nom_complet(p1), 
            "Cat1": c1,
            "J2": get_nom_complet(p2), 
            "Cat2": c2, 
            "Coeff": round(avg_coeff, 3)
        })
    
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

    if nouvelle_ronde_matchs:
        st.session_state.matchs = pd.concat([st.session_state.matchs, pd.DataFrame(nouvelle_ronde_matchs)], ignore_index=True)
        st.success(f"Ronde {prochaine_ronde} générée !")
    else:
        st.warning("Plus de combinaisons possibles sans répétition.")

# --- 4. INTERFACE UTILISATEUR ---
if st.session_state.bg_image_data:
    set_background(st.session_state.bg_image_data)
else:
    set_background(None)

# Affichage du titre du tournoi en haut de page
st.title(f"🏸 {st.session_state.nom_tournoi}")

tabs = st.tabs(["👥 Joueurs", "🤝 Équipes", "🏸 Matchs & Scores", "🏆 Classement", "⚙️ Paramètres"])

# -- JOUEURS --
with tabs[0]:
    st.subheader("Saisie des joueurs")
    
    # Afficher l'erreur si elle existe
    if st.session_state.erreur_saisie:
        st.error(st.session_state.erreur_saisie)
    
    # Ajouter un joueur temporaire
    col1, col2, col3, col4 = st.columns([2, 2, 3, 1])
    with col1:
        new_prenom = st.text_input("Prénom", key="input_prenom")
    with col2:
        new_nom = st.text_input("Nom", key="input_nom")
    with col3:
        new_cat = st.selectbox("Catégorie", options=list(st.session_state.categories_dict.keys()), key="input_cat")
    with col4:
        st.write("")
        st.write("")
        if st.button("➕ Ajouter"):
            # Vérifications avant d'ajouter
            prenom_clean = new_prenom.strip()
            nom_clean = new_nom.strip()
            
            if not prenom_clean or not nom_clean:
                st.session_state.erreur_saisie = "⚠️ Le prénom ET le nom doivent être renseignés !"
                st.rerun()
            elif joueur_existe(prenom_clean, nom_clean):
                st.session_state.erreur_saisie = f"⚠️ Le joueur {prenom_clean} {nom_clean} existe déjà dans la liste !"
                st.rerun()
            else:
                # Vérifier aussi dans les joueurs temporaires
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
    
    # Afficher les joueurs temporaires à valider
    if st.session_state.temp_joueurs:
        st.subheader("Joueurs à valider")
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
                    if st.button("✅", key=f"valid_{idx}"):
                        # Double vérification au moment de la validation
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
                    if st.button("🗑️", key=f"del_temp_{idx}"):
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
                if st.button("🗑️", key=f"del_joueur_{idx}"):
                    st.session_state.joueurs.pop(idx - 1)
                    st.rerun()
    else:
        st.info("Aucun joueur inscrit pour le moment.")
    
    st.divider()
    
    # Boutons de génération d'équipes
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔥 GÉNÉRER LES ÉQUIPES", use_container_width=True):
            generer_paires_equilibrees(mode="nouveau")
            st.rerun()
    with col2:
        joueurs_non_affectes = [j for j in st.session_state.joueurs 
                                if not joueur_dans_equipe(j['Prénom'], j['Nom'])]
        if len(joueurs_non_affectes) >= 2:
            if st.button("➕ AJOUTER DES ÉQUIPES", use_container_width=True):
                generer_paires_equilibrees(mode="ajouter")
                st.rerun()
        else:
            st.button("➕ AJOUTER DES ÉQUIPES", use_container_width=True, disabled=True, 
                     help="Il faut au moins 2 joueurs non affectés")

# -- ÉQUIPES --
with tabs[1]:
    st.subheader("Paires constituées")
    if not st.session_state.equipes.empty:
        st.dataframe(st.session_state.equipes, use_container_width=True)
    else:
        st.info("Les équipes apparaîtront ici après génération.")

# -- MATCHS --
with tabs[2]:
    col_a, col_b = st.columns([1, 1])
    if col_a.button("🎲 Lancer une nouvelle ronde"):
        generer_ronde_equitable()
        st.rerun()
    
    st.write(f"**Ronde actuelle : {get_current_round()}**")
    
    if not st.session_state.matchs.empty:
        st.session_state.matchs = st.data_editor(
            st.session_state.matchs,
            use_container_width=True,
            column_config={
                "Ronde": st.column_config.NumberColumn(disabled=True),
                "Terrain": st.column_config.TextColumn(disabled=True),
                "Equipe A": st.column_config.TextColumn(disabled=True),
                "Equipe B": st.column_config.TextColumn(disabled=True),
            },
            key="editeur_matchs"
        )

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
            else: # Standard
                score = (v * 2) + (n * 1)
            
            stats.append({
                "Équipe": eid, "Joueurs": f"{eq['J1']} & {eq['J2']}",
                "V": v, "N": n, "D": d, "Diff": diff, "Points": score
            })
        
        df_classement = pd.DataFrame(stats).sort_values(by=["Points", "Diff"], ascending=False)
        df_classement.index = range(1, len(df_classement) + 1)
        st.dataframe(df_classement, use_container_width=True)

# -- PARAMÈTRES --
with tabs[4]:
    st.subheader("⚙️ Configuration Générale")
    
    # Nom du tournoi
    nouveau_nom = st.text_input("Nom du Tournoi", st.session_state.nom_tournoi)
    if nouveau_nom != st.session_state.nom_tournoi:
        st.session_state.nom_tournoi = nouveau_nom
        st.rerun()
    
    st.session_state.nb_terrains = st.number_input("Nombre de terrains", 1, 50, st.session_state.nb_terrains)
    st.session_state.algo_classement = st.radio("Méthode de classement", ["Pondéré", "Standard"])
    
    st.divider()
    st.subheader("🏷️ Catégories et Coefficients")
    
    # Édition des catégories existantes
    for cat, coef in list(st.session_state.categories_dict.items()):
        c1, c2, c3 = st.columns([2, 2, 1])
        new_c = c2.number_input(f"Coeff {cat}", 0.5, 3.0, coef, 0.05, key=f"cfg_{cat}")
        st.session_state.categories_dict[cat] = new_c
        if c3.button("Supprimer", key=f"del_{cat}"):
            del st.session_state.categories_dict[cat]
            st.rerun()
            
    # Ajout d'une nouvelle catégorie
    with st.expander("➕ Ajouter une catégorie"):
        nc1, nc2 = st.columns(2)
        n_name = nc1.text_input("Nom (ex: Espoir)")
        n_coef = nc2.number_input("Coeff", 0.5, 3.0, 1.0, 0.05)
        if st.button("Enregistrer catégorie"):
            if n_name:
                st.session_state.categories_dict[n_name] = n_coef
                st.rerun()

    st.divider()
    st.subheader("🖼️ Personnalisation visuelle")
    
    img_fond = st.file_uploader("Image de fond (JPG/PNG)", type=["jpg", "jpeg", "png"])
    if img_fond:
        st.session_state.bg_image_data = img_fond
        st.rerun()
    
    # Bouton pour supprimer l'image de fond
    if st.session_state.bg_image_data is not None:
        if st.button("🗑️ Supprimer l'image de fond"):
            st.session_state.bg_image_data = None
            st.rerun()

    st.divider()
    if st.button("⌛ RÉINITIALISER TOUT LE TOURNOI"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()