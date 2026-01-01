""" 
DUCK MANAGER PRO - VERSION COMPLÈTE AVEC MODE INDIVIDUEL 
Copiez ce code dans un fichier app.py et lancez avec: streamlit run app.py 

MODIFICATIONS APPORTÉES: 
✅ Vérification des surnoms d'équipe en doublon 
✅ Affichage immédiat après import de joueurs 
✅ Import d'équipes possible sans équipes existantes 
✅ Suppression unitaire des équipes (si pas dans un round) 
✅ Vérification des joueurs lors de l'import d'équipes (mode append) 
✅ Import/export des matchs avec vérification des équipes + confirmation 
✅ Export Excel (xlsx) pour le classement 
✅ Export PDF pour équipes et rounds 
✅ Remplacement "ronde" par "round" partout 
✅ Import/export des paramètres avec application immédiate 
✅ BUG CORRIGÉ : Bouton importation équipes visible avec joueurs et organisateur 
✅ BUG CORRIGÉ : Bouton importation matchs visible avec 2+ équipes et organisateur 
✅ MEILLEURE UX : Affichage données en haut, importation en bas 
✅ NOUVEAU : Mode tournoi individuel avec équipes aléatoires 
✅ NOUVEAU : Classement individuel basé sur la différence de points 
✅ NOUVEAU : Génération d'équipes aléatoires pour le mode individuel 
✅ CORRECTION : Problème d'affichage des scores en mode individuel 
✅ CORRECTION : Génération d'équipes aléatoires fonctionnelle 
""" 

import streamlit as st 
import pandas as pd 
import random 
import base64 
import io 
import json 
from datetime import datetime 
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
    
    # MODIFICATION IMPORTANTE : Nouvelle structure pour mode individuel 
    'equipes_fixes': pd.DataFrame(columns=["ID", "Surnom", "J1", "Cat1", "J2", "Cat2", "Coeff"]), 
    'historique_equipes': pd.DataFrame(columns=["Round", "ID", "Surnom", "J1", "Cat1", "J2", "Cat2", "Coeff"]), 
    
    # Compatibilité avec l'ancien code - AJOUT IMPORTANT 
    'equipes': pd.DataFrame(columns=["ID", "Surnom", "J1", "Cat1", "J2", "Cat2", "Coeff"]), 
    
    # Nouvelle structure de matchs avec joueurs 
    'matchs_detail': pd.DataFrame(columns=[ 
        "Round", "Terrain",  
        "Equipe_A_ID", "J1_A", "J2_A", "Score_A", 
        "Equipe_B_ID", "J1_B", "J2_B", "Score_B" 
    ]), 
    
    # Compatibilité avec ancien code 
    'matchs': pd.DataFrame(columns=["Round", "Terrain", "Equipe A", "Score A", "Equipe B", "Score B"]), 
    
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
    'pending_matchs_import': None 
}

# === FONCTIONS === 

def set_background(f): 
    if f: 
        st.markdown(f'<style>.stApp{{background-image:url("data:image/jpeg;base64,{base64.b64encode(f.getvalue()).decode()}");background-size:cover;background-attachment:fixed;}}</style>', unsafe_allow_html=True) 
    else: 
        st.markdown('<style>.stApp{background-image:none;background-color:white;}</style>', unsafe_allow_html=True) 

def get_current_round(): 
    return 0 if st.session_state.matchs.empty else int(st.session_state.matchs["Round"].max()) 

def joueur_existe(p, n): 
    return any(j['Prénom'].lower().strip()==p.lower().strip() and j['Nom'].lower().strip()==n.lower().strip() for j in st.session_state.joueurs) 

def joueur_dans_equipe(p, n): 
    if st.session_state.equipes.empty: 
        return False 
    nc = f"{p} {n}" 
    return nc in st.session_state.equipes['J1'].values or nc in st.session_state.equipes['J2'].values 

def get_nom_complet(j): 
    return f"{j['Prénom']} {j['Nom']}" 

def est_organisateur(): 
    return st.session_state.profil == "Organisateur" 

def est_joker(nom): 
    return "Joker" in nom 

def get_nom_affichage_equipe(eq): 
    return eq['Surnom'] if pd.notna(eq['Surnom']) and eq['Surnom'].strip() else eq['ID'] 

def surnom_existe_deja(s, curr_id=None): 
    if st.session_state.equipes.empty or not s or not s.strip(): 
        return False 
    s = s.strip() 
    for _, eq in st.session_state.equipes.iterrows(): 
        if eq['ID'] != curr_id and pd.notna(eq['Surnom']) and eq['Surnom'].strip().lower() == s.lower(): 
            return True 
    return False 

def equipe_dans_matchs(eid): 
    if st.session_state.matchs.empty: 
        return False 
    return eid in st.session_state.matchs['Equipe A'].values or eid in st.session_state.matchs['Equipe B'].values 

def get_details_equipe(eid): 
    """Retourne les détails d'une équipe à partir de son ID""" 
    eq = st.session_state.equipes[st.session_state.equipes['ID'] == eid] 
    if eq.empty: 
        return None, None, None, None, None 
    eq = eq.iloc[0] 
    
    # Séparer les noms complets en prénom et nom 
    prenom1, nom1 = split_nom_complet(eq['J1']) 
    prenom2, nom2 = split_nom_complet(eq['J2']) 
    
    return get_nom_affichage_equipe(eq), prenom1, nom1, prenom2, nom2 

def split_nom_complet(nom_complet): 
    """Sépare un nom complet en prénom et nom""" 
    if not isinstance(nom_complet, str): 
        return "", "" 
    
    # Gérer les jokers 
    if "Joker" in nom_complet: 
        return nom_complet, "" 
    
    # Séparer prénom et nom 
    parts = nom_complet.split(' ', 1) 
    if len(parts) == 2: 
        return parts[0].strip(), parts[1].strip() 
    return nom_complet.strip(), "" 

def get_categorie_joueur(nom_complet): 
    """Retourne la catégorie d'un joueur à partir de son nom complet""" 
    if not isinstance(nom_complet, str): 
        return "Joker" 
    
    if "Joker" in nom_complet: 
        return "Joker" 
    
    for joueur in st.session_state.joueurs: 
        if get_nom_complet(joueur) == nom_complet: 
            return joueur['Catégorie'] 
    return "Joker" 

# === IMPORT/EXPORT === 
def exporter_parametres(): 
    params = { 
        'nom_tournoi': st.session_state.nom_tournoi, 
        'nb_terrains': st.session_state.nb_terrains, 
        'algo_classement': st.session_state.algo_classement, 
        'algo_classement_individuel': st.session_state.algo_classement_individuel, 
        'mode_tournoi': st.session_state.mode_tournoi, 
        'categories_dict': st.session_state.categories_dict 
    } 
    return json.dumps(params, ensure_ascii=False, indent=2).encode('utf-8') 

def importer_parametres(f): 
    try: 
        p = json.loads(f.getvalue().decode('utf-8')) 
        st.session_state.nom_tournoi = p.get('nom_tournoi', st.session_state.nom_tournoi) 
        st.session_state.nb_terrains = p.get('nb_terrains', st.session_state.nb_terrains) 
        st.session_state.algo_classement = p.get('algo_classement', st.session_state.algo_classement) 
        st.session_state.algo_classement_individuel = p.get('algo_classement_individuel', st.session_state.algo_classement_individuel) 
        st.session_state.mode_tournoi = p.get('mode_tournoi', st.session_state.mode_tournoi) 
        st.session_state.categories_dict = p.get('categories_dict', st.session_state.categories_dict) 
        return True, "✅ Paramètres importés avec succès!" 
    except Exception as e: 
        return False, f"❌ Erreur: {e}" 

def generer_excel_classement(): 
    if st.session_state.matchs.empty: 
        return None 
    stats = [] 
    for _, eq in st.session_state.equipes.iterrows(): 
        eid = eq["ID"] 
        m_eq = st.session_state.matchs[(st.session_state.matchs["Equipe A"]==eid)|(st.session_state.matchs["Equipe B"]==eid)] 
        pm, pe, v, n, d = 0, 0, 0, 0, 0 
        for _, m in m_eq.iterrows(): 
            if m["Score A"]==0 and m["Score B"]==0: 
                continue 
            is_a = m["Equipe A"]==eid 
            ma, sa = (m["Score A"], m["Score B"]) if is_a else (m["Score B"], m["Score A"]) 
            pm += ma 
            pe += sa 
            if ma>sa: 
                v+=1 
            elif ma==sa: 
                n+=1 
            else: 
                d+=1 
        diff = pm - pe 
        if st.session_state.algo_classement=="Pondéré": 
            score = round(((v*3)+(n*1))*eq["Coeff"], 2) 
        else: 
            score = (v*2)+(n*1) 
        stats.append({ 
            "Équipe": get_nom_affichage_equipe(eq), 
            "Joueurs": f"{eq['J1']} & {eq['J2']}", 
            "V": v, "N": n, "D": d, "Diff": diff, "Points": score 
        }) 
    df = pd.DataFrame(stats).sort_values(by=["Points", "Diff"], ascending=False) 
    df.index = range(1, len(df)+1) 
    df.index.name = "Rang" 
    buf = io.BytesIO() 
    with pd.ExcelWriter(buf, engine='openpyxl') as w: 
        df.to_excel(w, sheet_name='Classement') 
    buf.seek(0) 
    return buf.getvalue() 

def generer_pdf_classement(): 
    buf = io.BytesIO() 
    doc = SimpleDocTemplate(buf, pagesize=A4) 
    els, sty = [], getSampleStyleSheet() 
    els.append(Paragraph(f"Classement - {st.session_state.nom_tournoi}", sty['Title'])) 
    els.append(Paragraph(f"Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}", sty['Normal'])) 
    els.append(Spacer(1, 20)) 
    if not st.session_state.matchs.empty: 
        stats = [] 
        for _, eq in st.session_state.equipes.iterrows(): 
            eid = eq["ID"] 
            m_eq = st.session_state.matchs[(st.session_state.matchs["Equipe A"]==eid)|(st.session_state.matchs["Equipe B"]==eid)] 
            pm, pe, v, n, d = 0, 0, 0, 0, 0 
            for _, m in m_eq.iterrows(): 
                if m["Score A"]==0 and m["Score B"]==0: 
                    continue 
                is_a = m["Equipe A"]==eid 
                ma, sa = (m["Score A"], m["Score B"]) if is_a else (m["Score B"], m["Score A"]) 
                pm += ma 
                pe += sa 
                if ma>sa: 
                    v+=1 
                elif ma==sa: 
                    n+=1 
                else: 
                    d+=1 
            diff = pm - pe 
            if st.session_state.algo_classement=="Pondéré": 
                score = round(((v*3)+(n*1))*eq["Coeff"], 2) 
            else: 
                score = (v*2)+(n*1) 
            stats.append([get_nom_affichage_equipe(eq), f"{eq['J1']} & {eq['J2']}", v, n, d, diff, score]) 
        stats.sort(key=lambda x: (x[6], x[5]), reverse=True) 
        data = [["Rang", "Équipe", "Joueurs", "V", "N", "D", "Diff", "Points"]] 
        for i, r in enumerate(stats, 1): 
            data.append([i] + r) 
        tbl = Table(data) 
        tbl.setStyle(TableStyle([ 
            ('BACKGROUND',(0,0),(-1,0),colors.grey), 
            ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke), 
            ('ALIGN',(0,0),(-1,-1),'CENTER'), 
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'), 
            ('GRID',(0,0),(-1,-1),1,colors.black) 
        ])) 
        els.append(tbl) 
    doc.build(els) 
    buf.seek(0) 
    return buf 

def generer_pdf_equipes(): 
    """Génère un PDF des équipes (version compatible avec les deux modes)""" 
    buf = io.BytesIO() 
    doc = SimpleDocTemplate(buf, pagesize=A4) 
    els, sty = [], getSampleStyleSheet() 
    
    els.append(Paragraph(f"Équipes - {st.session_state.nom_tournoi}", sty['Title'])) 
    els.append(Paragraph(f"Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}", sty['Normal'])) 
    els.append(Paragraph(f"Mode: {st.session_state.mode_tournoi}", sty['Normal'])) 
    els.append(Spacer(1, 20)) 
    
    if st.session_state.mode_tournoi == "Classique": 
        # Afficher les équipes fixes 
        if not st.session_state.equipes_fixes.empty: 
            data = [["ID", "Surnom", "J1", "Cat1", "J2", "Cat2", "Coeff"]] 
            for _, eq in st.session_state.equipes_fixes.iterrows(): 
                data.append([eq['ID'], get_nom_affichage_equipe(eq), eq['J1'], eq['Cat1'], eq['J2'], eq['Cat2'], eq['Coeff']]) 
    else: 
        # Mode individuel : afficher les équipes du dernier round 
        equipes_actuelles = get_equipes_actuelles() 
        if not equipes_actuelles.empty: 
            data = [["ID", "Surnom", "J1", "Cat1", "J2", "Cat2", "Coeff"]] 
            for _, eq in equipes_actuelles.iterrows(): 
                data.append([eq['ID'], get_nom_affichage_equipe(eq), eq['J1'], eq['Cat1'], eq['J2'], eq['Cat2'], eq['Coeff']]) 
        else: 
            data = [] 
    
    if data: 
        tbl = Table(data) 
        tbl.setStyle(TableStyle([ 
            ('BACKGROUND',(0,0),(-1,0),colors.grey), 
            ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke), 
            ('ALIGN',(0,0),(-1,-1),'CENTER'), 
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'), 
            ('GRID',(0,0),(-1,-1),1,colors.black) 
        ])) 
        els.append(tbl) 
    
    doc.build(els) 
    buf.seek(0) 
    return buf 

def generer_pdf_rounds(): 
    """Génère un PDF des rounds (version compatible avec les deux modes)""" 
    buf = io.BytesIO() 
    doc = SimpleDocTemplate(buf, pagesize=A4) 
    els, sty = [], getSampleStyleSheet() 
    els.append(Paragraph(f"Rounds - {st.session_state.nom_tournoi}", sty['Title'])) 
    els.append(Paragraph(f"Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}", sty['Normal'])) 
    els.append(Spacer(1, 20)) 
    
    if not st.session_state.matchs.empty: 
        for rn in sorted(st.session_state.matchs['Round'].unique()): 
            els.append(Paragraph(f"<b>Round {rn}</b>", sty['Heading2'])) 
            els.append(Spacer(1, 10)) 
            mr = st.session_state.matchs[st.session_state.matchs['Round']==rn] 
            data = [["Terrain", "Équipe A", "Score A", "Score B", "Équipe B"]] 
            
            for _, m in mr.iterrows(): 
                # Récupérer les équipes selon le mode 
                if st.session_state.mode_tournoi == "Classique": 
                    ea = st.session_state.equipes_fixes[st.session_state.equipes_fixes['ID']==m['Equipe A']] 
                    eb = st.session_state.equipes_fixes[st.session_state.equipes_fixes['ID']==m['Equipe B']] 
                else: 
                    # Mode individuel : chercher dans l'historique 
                    equipes_round = get_equipes_par_round(rn) 
                    ea = equipes_round[equipes_round['ID']==m['Equipe A']] if not equipes_round.empty else pd.DataFrame() 
                    eb = equipes_round[equipes_round['ID']==m['Equipe B']] if not equipes_round.empty else pd.DataFrame() 
                
                na = get_nom_affichage_equipe(ea.iloc[0]) if not ea.empty else m['Equipe A'] 
                nb = get_nom_affichage_equipe(eb.iloc[0]) if not eb.empty else m['Equipe B'] 
                data.append([m['Terrain'], na, m['Score A'], m['Score B'], nb]) 
            
            # Créer la table pour CE round 
            tbl = Table(data) 
            tbl.setStyle(TableStyle([ 
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey), 
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke), 
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'), 
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), 
                ('GRID', (0, 0), (-1, -1), 1, colors.black) 
            ])) 
            els.append(tbl) 
            els.append(Spacer(1, 20)) 
    
    doc.build(els) 
    buf.seek(0) 
    return buf 

def exporter_rounds_csv(): 
    """Exporte les rounds avec tous les détails des joueurs""" 
    if st.session_state.matchs.empty: 
        return None 
    
    rows = [] 
    for _, m in st.session_state.matchs.iterrows(): 
        # Détails équipe A 
        surnomA, p1A, n1A, p2A, n2A = get_details_equipe(m['Equipe A']) 
        # Détails équipe B 
        surnomB, p1B, n1B, p2B, n2B = get_details_equipe(m['Equipe B']) 
        
        rows.append({ 
            "Round": m['Round'], 
            "Terrain": m['Terrain'], 
            "Surnom Équipe A": surnomA if surnomA else m['Equipe A'], 
            "Prénom1A": p1A, "Nom1A": n1A, 
            "Prénom2A": p2A, "Nom2A": n2A, 
            "Score A": m['Score A'], 
            "Score B": m['Score B'], 
            "Surnom Équipe B": surnomB if surnomB else m['Equipe B'], 
            "Prénom1B": p1B, "Nom1B": n1B, 
            "Prénom2B": p2B, "Nom2B": n2B 
        }) 
    
    df = pd.DataFrame(rows) 
    return df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig') 

def exporter_rounds_xlsx(): 
    """Exporte les rounds en format Excel avec tous les détails""" 
    if st.session_state.matchs.empty: 
        return None 
    
    rows = [] 
    for _, m in st.session_state.matchs.iterrows(): 
        # Détails équipe A 
        surnomA, p1A, n1A, p2A, n2A = get_details_equipe(m['Equipe A']) 
        # Détails équipe B 
        surnomB, p1B, n1B, p2B, n2B = get_details_equipe(m['Equipe B']) 
        
        rows.append({ 
            "Round": m['Round'], 
            "Terrain": m['Terrain'], 
            "Surnom Équipe A": surnomA if surnomA else m['Equipe A'], 
            "Prénom1A": p1A, "Nom1A": n1A, 
            "Prénom2A": p2A, "Nom2A": n2A, 
            "Score A": m['Score A'], 
            "Score B": m['Score B'], 
            "Surnom Équipe B": surnomB if surnomB else m['Equipe B'], 
            "Prénom1B": p1B, "Nom1B": n1B, 
            "Prénom2B": p2B, "Nom2B": n2B 
        }) 
    
    df = pd.DataFrame(rows) 
    output = io.BytesIO() 
    with pd.ExcelWriter(output, engine='openpyxl') as writer: 
        df.to_excel(writer, sheet_name='Rounds', index=False) 
        
        # Ajuster la largeur des colonnes 
        worksheet = writer.sheets['Rounds'] 
        for i, col in enumerate(df.columns): 
            column_width = max(df[col].astype(str).map(len).max(), len(col)) + 2 
            worksheet.column_dimensions[chr(65 + i)].width = min(column_width, 30) 
    
    return output.getvalue() 

# === NOUVELLES FONCTIONS POUR LE MODE INDIVIDUEL === 
def calculer_classement_individuel(): 
    """ 
    Calcule le classement individuel basé sur la différence de points 
    Prend en compte tous les matchs même si le joueur a changé d'équipe 
    """ 
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
        
        # Points pour les deux équipes 
        points_a = match["Score_A"] 
        points_b = match["Score_B"] 
        
        # Équipe A 
        for joueur_nom in [match['J1_A'], match['J2_A']]: 
            if joueur_nom in stats_joueurs: 
                stats = stats_joueurs[joueur_nom] 
                stats["Matchs Joués"] += 1 
                stats["Points Marqués"] += points_a 
                stats["Points Encaissés"] += points_b 
                diff_match = points_a - points_b 
                stats["Différence"] += diff_match 
                
                # Calcul pondéré (nécessite le coefficient de l'équipe) 
                if st.session_state.algo_classement_individuel == "Pondéré": 
                    # Récupérer le coefficient de l'équipe 
                    coeff = 1.0 
                    # Chercher l'équipe dans l'historique 
                    round_num = match['Round'] 
                    equipes_round = get_equipes_par_round(round_num) 
                    if not equipes_round.empty: 
                        eq = equipes_round[equipes_round['ID'] == match['Equipe_A_ID']] 
                        if not eq.empty: 
                            coeff = eq.iloc[0]['Coeff'] 
                    stats["Score Pondéré"] += diff_match * coeff 
                else: 
                    stats["Score Pondéré"] += diff_match 
        
        # Équipe B 
        for joueur_nom in [match['J1_B'], match['J2_B']]: 
            if joueur_nom in stats_joueurs: 
                stats = stats_joueurs[joueur_nom] 
                stats["Matchs Joués"] += 1 
                stats["Points Marqués"] += points_b 
                stats["Points Encaissés"] += points_a 
                diff_match = points_b - points_a 
                stats["Différence"] += diff_match 
                
                # Calcul pondéré 
                if st.session_state.algo_classement_individuel == "Pondéré": 
                    coeff = 1.0 
                    round_num = match['Round'] 
                    equipes_round = get_equipes_par_round(round_num) 
                    if not equipes_round.empty: 
                        eq = equipes_round[equipes_round['ID'] == match['Equipe_B_ID']] 
                        if not eq.empty: 
                            coeff = eq.iloc[0]['Coeff'] 
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

def generer_pdf_classement_individuel(): 
    buf = io.BytesIO() 
    doc = SimpleDocTemplate(buf, pagesize=A4) 
    els, sty = [], getSampleStyleSheet() 
    
    els.append(Paragraph(f"Classement Individuel - {st.session_state.nom_tournoi}", sty['Title'])) 
    els.append(Paragraph(f"Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}", sty['Normal'])) 
    els.append(Paragraph(f"Méthode: {st.session_state.algo_classement_individuel}", sty['Normal'])) 
    els.append(Spacer(1, 20)) 
    
    df_classement = calculer_classement_individuel() 
    
    if not df_classement.empty: 
        data = [["Rang", "Joueur", "Catégorie", "MJ", "PM", "PE", "Diff", "Score"]] 
        
        for idx, row in df_classement.iterrows(): 
            data.append([ 
                idx, 
                row["Joueur"], 
                row["Catégorie"], 
                row["MJ"], 
                row["PM"], 
                row["PE"], 
                row["Diff"], 
                row["Score"] 
            ]) 
        
        tbl = Table(data) 
        tbl.setStyle(TableStyle([ 
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey), 
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke), 
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'), 
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), 
            ('FONTSIZE', (0, 0), (-1, -1), 9), 
            ('GRID', (0, 0), (-1, -1), 1, colors.black) 
        ])) 
        els.append(tbl) 
    else: 
        els.append(Paragraph("Aucune donnée disponible", sty['Normal'])) 
    
    doc.build(els) 
    buf.seek(0) 
    return buf 

def exporter_matchs_detail_csv(): 
    """Exporte les matchs avec tous les détails des joueurs""" 
    if st.session_state.matchs_detail.empty: 
        return None 
    
    # Copier les données 
    df_export = st.session_state.matchs_detail.copy() 
    
    # Renommer les colonnes pour plus de clarté 
    df_export = df_export.rename(columns={ 
        'Equipe_A_ID': 'ID Équipe A', 
        'J1_A': 'Joueur 1 Équipe A', 
        'J2_A': 'Joueur 2 Équipe A', 
        'Equipe_B_ID': 'ID Équipe B', 
        'J1_B': 'Joueur 1 Équipe B', 
        'J2_B': 'Joueur 2 Équipe B' 
    }) 
    
    return df_export.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig') 

def exporter_matchs_detail_xlsx(): 
    """Exporte les matchs en format Excel avec tous les détails""" 
    if st.session_state.matchs_detail.empty: 
        return None 
    
    # Préparer les données 
    df_export = st.session_state.matchs_detail.copy() 
    
    # Renommer les colonnes 
    df_export = df_export.rename(columns={ 
        'Equipe_A_ID': 'ID Équipe A', 
        'J1_A': 'Joueur 1 Équipe A', 
        'J2_A': 'Joueur 2 Équipe A', 
        'Equipe_B_ID': 'ID Équipe B', 
        'J1_B': 'Joueur 1 Équipe B', 
        'J2_B': 'Joueur 2 Équipe B' 
    }) 
    
    output = io.BytesIO() 
    with pd.ExcelWriter(output, engine='openpyxl') as writer: 
        df_export.to_excel(writer, sheet_name='Matchs Détaillés', index=False) 
        
        # Ajuster la largeur des colonnes 
        worksheet = writer.sheets['Matchs Détaillés'] 
        for i, col in enumerate(df_export.columns): 
            column_width = max(df_export[col].astype(str).map(len).max(), len(col)) + 2 
            worksheet.column_dimensions[chr(65 + i)].width = min(column_width, 30) 
    
    return output.getvalue() 

def generer_pdf_rounds_detail(): 
    """Génère un PDF détaillé des rounds avec les noms des joueurs""" 
    buf = io.BytesIO() 
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20, rightMargin=20) 
    els, sty = [], getSampleStyleSheet() 
    
    # Titre 
    els.append(Paragraph(f"Rounds Détaillés - {st.session_state.nom_tournoi}", sty['Title'])) 
    els.append(Paragraph(f"Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}", sty['Normal'])) 
    els.append(Paragraph(f"Mode: {st.session_state.mode_tournoi}", sty['Normal'])) 
    els.append(Spacer(1, 20)) 
    
    if not st.session_state.matchs_detail.empty: 
        for rn in sorted(st.session_state.matchs_detail['Round'].unique()): 
            # Titre du round 
            els.append(Paragraph(f"<b>Round {rn}</b>", sty['Heading2'])) 
            els.append(Spacer(1, 10)) 
            
            # Récupérer les matchs de ce round 
            mr = st.session_state.matchs_detail[st.session_state.matchs_detail['Round'] == rn] 
            
            # Préparer les données du tableau 
            data = [["Terrain", "Équipe A", "Joueurs A", "Score A", "Score B", "Équipe B", "Joueurs B"]] 
            
            for _, m in mr.iterrows(): 
                # Récupérer les noms d'équipes avec surnoms 
                equipes_round = get_equipes_par_round(rn) 
                
                nom_equipe_a = m['Equipe_A_ID'] 
                nom_equipe_b = m['Equipe_B_ID'] 
                
                if not equipes_round.empty: 
                    eq_a = equipes_round[equipes_round['ID'] == m['Equipe_A_ID']] 
                    eq_b = equipes_round[equipes_round['ID'] == m['Equipe_B_ID']] 
                    
                    if not eq_a.empty: 
                        nom_equipe_a = get_nom_affichage_equipe(eq_a.iloc[0]) 
                    if not eq_b.empty: 
                        nom_equipe_b = get_nom_affichage_equipe(eq_b.iloc[0]) 
                
                # Formater les joueurs 
                joueurs_a = f"{m['J1_A']}\n{m['J2_A']}" 
                joueurs_b = f"{m['J1_B']}\n{m['J2_B']}" 
                
                data.append([ 
                    m['Terrain'], 
                    nom_equipe_a, 
                    joueurs_a, 
                    str(m['Score_A']), 
                    str(m['Score_B']), 
                    nom_equipe_b, 
                    joueurs_b 
                ]) 
            
            # Créer le tableau 
            tbl = Table(data, colWidths=[30, 50, 70, 25, 25, 50, 70]) 
            tbl.setStyle(TableStyle([ 
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4B8BBE')), 
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke), 
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'), 
                ('ALIGN', (2, 1), (2, -1), 'LEFT'), 
                ('ALIGN', (6, 1), (6, -1), 'LEFT'), 
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), 
                ('FONTSIZE', (0, 0), (-1, -1), 8), 
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black), 
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), 
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F0F0F0')]) 
            ])) 
            
            els.append(tbl) 
            els.append(Spacer(1, 20)) 
    
    doc.build(els) 
    buf.seek(0) 
    return buf 

def get_equipes_actuelles(): 
    """Retourne les équipes actuelles selon le mode""" 
    if st.session_state.mode_tournoi == "Classique": 
        return st.session_state.equipes_fixes 
    else: 
        # Retourner les équipes du round actuel (dernier round de l'historique) 
        if st.session_state.historique_equipes.empty: 
            return pd.DataFrame() 
        dernier_round = st.session_state.historique_equipes["Round"].max() 
        return st.session_state.historique_equipes[ 
            st.session_state.historique_equipes["Round"] == dernier_round 
        ].drop(columns=["Round"]) 

def get_equipes_par_round(round_num): 
    """Retourne les équipes d'un round spécifique""" 
    if st.session_state.historique_equipes.empty: 
        return pd.DataFrame() 
    return st.session_state.historique_equipes[ 
        st.session_state.historique_equipes["Round"] == round_num 
    ].drop(columns=["Round"]) 

# === GÉNÉRATION === 
def generer_paires_equilibrees(mode="nouveau"): 
    ja = [j for j in st.session_state.joueurs if j['Prénom'].strip() and j['Nom'].strip() and j['Catégorie']!="Joker" and (mode=="nouveau" or not joueur_dans_equipe(j['Prénom'], j['Nom']))] 
    if len(ja)<1 and mode=="ajouter": 
        st.error("Aucun joueur non affecté") 
        return 
    if len(ja)<2 and mode=="nouveau": 
        st.error("Il faut au moins 2 joueurs") 
        return 
    if mode=="nouveau": 
        st.session_state.equipes = pd.DataFrame(columns=["ID", "Surnom", "J1", "Cat1", "J2", "Cat2", "Coeff"]) 
        # Synchroniser avec equipes_fixes pour le mode classique 
        if st.session_state.mode_tournoi == "Classique": 
            st.session_state.equipes_fixes = pd.DataFrame(columns=["ID", "Surnom", "J1", "Cat1", "J2", "Cat2", "Coeff"]) 
    jt = sorted(ja, key=lambda x: st.session_state.categories_dict[x['Catégorie']], reverse=True) 
    jaj = jt.pop() if len(jt)%2 else None 
    pairs = [] 
    while len(jt)>=2: 
        pairs.append((jt.pop(0), jt.pop(-1))) 
    sid = 1 if mode=="nouveau" or st.session_state.equipes.empty else max([int(e.replace("Équipe ", "")) for e in st.session_state.equipes["ID"]])+1 
    nt = [] 
    for i, (p1, p2) in enumerate(pairs, sid): 
        c1, c2 = p1['Catégorie'], p2['Catégorie'] 
        eid = f"Équipe {i}" 
        nt.append({ 
            "ID": eid, "Surnom": eid, 
            "J1": get_nom_complet(p1), "Cat1": c1, 
            "J2": get_nom_complet(p2), "Cat2": c2, 
            "Coeff": round((st.session_state.categories_dict[c1]+st.session_state.categories_dict[c2])/2, 3) 
        }) 
    if jaj: 
        i = sid+len(pairs) 
        eid = f"Équipe {i}" 
        c1 = jaj['Catégorie'] 
        nt.append({ 
            "ID": eid, "Surnom": eid, 
            "J1": get_nom_complet(jaj), "Cat1": c1, 
            "J2": f"Joker {i}", "Cat2": "Joker", 
            "Coeff": round((st.session_state.categories_dict[c1]+1.0)/2, 3) 
        }) 
        st.warning(f"⚠️ Joueur impair: {get_nom_complet(jaj)} avec Joker") 
    if nt: 
        st.session_state.equipes = pd.concat([st.session_state.equipes, pd.DataFrame(nt)], ignore_index=True) if mode=="ajouter" else pd.DataFrame(nt) 
        # Synchroniser avec equipes_fixes pour le mode classique 
        if st.session_state.mode_tournoi == "Classique": 
            st.session_state.equipes_fixes = st.session_state.equipes.copy() 
        st.success(f"✅ {len(nt)} équipes {'ajoutées' if mode=='ajouter' else 'créées'}!") 

def generer_equipes_aleatoires_mode_individuel(): 
    """Génère des équipes aléatoires pour le mode individuel et les stocke""" 
    if len(st.session_state.joueurs) < 2: 
        st.error("Il faut au moins 2 joueurs pour créer des équipes") 
        return False
    
    # Créer des équipes pour le round 0 (équipes initiales)
    joueurs = [get_nom_complet(j) for j in st.session_state.joueurs]
    random.shuffle(joueurs)
    
    equipes_round = []
    round_num = 0  # Round 0 pour les équipes initiales
    
    for i in range(0, len(joueurs), 2):
        if i + 1 < len(joueurs):
            equipe_id = f"R{round_num}_E{i//2+1}"
            
            # Récupérer les catégories 
            cat1 = get_categorie_joueur(joueurs[i])
            cat2 = get_categorie_joueur(joueurs[i+1])
            
            equipes_round.append({
                "Round": round_num,
                "ID": equipe_id,
                "Surnom": equipe_id,
                "J1": joueurs[i],
                "Cat1": cat1,
                "J2": joueurs[i+1],
                "Cat2": cat2,
                "Coeff": round((st.session_state.categories_dict.get(cat1, 1.0) +  
                               st.session_state.categories_dict.get(cat2, 1.0)) / 2, 3)
            })
        else:
            # Joueur impair -> avec joker
            equipe_id = f"R{round_num}_E{i//2+1}"
            cat1 = get_categorie_joueur(joueurs[i])
            
            equipes_round.append({
                "Round": round_num,
                "ID": equipe_id,
                "Surnom": equipe_id,
                "J1": joueurs[i],
                "Cat1": cat1,
                "J2": f"Joker_R{round_num}",
                "Cat2": "Joker",
                "Coeff": round((st.session_state.categories_dict.get(cat1, 1.0) + 1.0) / 2, 3)
            })
            st.warning(f"⚠️ Joueur impair: {joueurs[i]} avec Joker")
    
    # Stocker dans l'historique
    df_equipes_round = pd.DataFrame(equipes_round)
    st.session_state.historique_equipes = pd.concat([
        st.session_state.historique_equipes,  
        df_equipes_round
    ], ignore_index=True)
    
    # Afficher un message de succès
    st.success(f"✅ {len(equipes_round)} équipes aléatoires créées pour le round 0!")
    return True
        
def generer_equipes_aleatoires(mode="nouveau", round_num=None): 
    """ 
    Génère des équipes aléatoires pour le mode tournoi individuel 
    round_num : numéro du round (pour générer des ID uniques) 
    """ 
    # Cette fonction est maintenant utilisée uniquement pour le mode classique
    # Pour le mode individuel, on utilise generer_equipes_aleatoires_mode_individuel
    
    # Filtrer les joueurs disponibles 
    if mode == "nouveau": 
        ja = [j for j in st.session_state.joueurs if j['Prénom'].strip() and j['Nom'].strip() and j['Catégorie']!="Joker"] 
    else:  # mode "ajouter" 
        ja = [j for j in st.session_state.joueurs if j['Prénom'].strip() and j['Nom'].strip()  
              and j['Catégorie']!="Joker" and not joueur_dans_equipe(j['Prénom'], j['Nom'])] 
    
    if len(ja) < 1: 
        st.error("Aucun joueur disponible pour créer des équipes") 
        return [] 
    
    # Mélanger aléatoirement la liste des joueurs 
    joueurs_melanges = ja.copy() 
    random.shuffle(joueurs_melanges) 
    
    # Créer les paires 
    pairs = [] 
    while len(joueurs_melanges) >= 2: 
        pairs.append((joueurs_melanges.pop(0), joueurs_melanges.pop(0))) 
    
    # Gérer un joueur impair 
    joueur_impair = joueurs_melanges.pop(0) if joueurs_melanges else None 
    
    # Déterminer le prochain ID d'équipe 
    if round_num is None: 
        # Pour mode classique 
        if mode == "nouveau" or st.session_state.equipes_fixes.empty: 
            sid = 1 
        else: 
            ids_existants = [int(e.replace("Équipe ", "")) for e in st.session_state.equipes_fixes["ID"]  
                            if isinstance(e, str) and e.startswith("Équipe ")] 
            sid = max(ids_existants) + 1 if ids_existants else 1 
        prefix = "Équipe " 
    else: 
        # Pour mode individuel 
        prefix = f"R{round_num}E" 
        sid = 1 
    
    # Créer les équipes 
    nouvelles_equipes = [] 
    for i, (p1, p2) in enumerate(pairs, sid): 
        c1, c2 = p1['Catégorie'], p2['Catégorie'] 
        eid = f"{prefix}{i}" 
        
        nouvelles_equipes.append({ 
            "ID": eid,  
            "Surnom": eid, 
            "J1": get_nom_complet(p1),  
            "Cat1": c1, 
            "J2": get_nom_complet(p2),  
            "Cat2": c2, 
            "Coeff": round((st.session_state.categories_dict[c1] + st.session_state.categories_dict[c2]) / 2, 3) 
        }) 
    
    # Ajouter l'équipe avec joker si joueur impair 
    if joueur_impair: 
        i = sid + len(pairs) 
        eid = f"{prefix}{i}" 
        c1 = joueur_impair['Catégorie'] 
        nouvelles_equipes.append({ 
            "ID": eid,  
            "Surnom": eid, 
            "J1": get_nom_complet(joueur_impair),  
            "Cat1": c1, 
            "J2": f"Joker {i}",  
            "Cat2": "Joker", 
            "Coeff": round((st.session_state.categories_dict[c1] + 1.0) / 2, 3) 
        }) 
    
    return nouvelles_equipes 

def generer_round_equitable(): 
    """Version unifiée pour les deux modes""" 
    if st.session_state.mode_tournoi == "Individuel": 
        generer_round_individuel_complet() 
    else: 
        generer_round_classique() 

def generer_round_classique(): 
    """Génère un round en mode classique (équipes fixes)""" 
    if st.session_state.equipes_fixes.empty: 
        st.error("Générez d'abord les équipes") 
        return 
    
    tids = st.session_state.equipes_fixes["ID"].tolist() 
    sj = {t: 0 for t in tids} 
    hist = {t: set() for t in tids} 
    
    if not st.session_state.matchs.empty: 
        for _, r in st.session_state.matchs.iterrows(): 
            sj[r["Equipe A"]] += 1 
            sj[r["Equipe B"]] += 1 
            hist[r["Equipe A"]].add(r["Equipe B"]) 
            hist[r["Equipe B"]].add(r["Equipe A"]) 
    
    # Vérifier si on a assez de terrains 
    nb_equipes = len(tids) 
    if nb_equipes / 2 > st.session_state.nb_terrains: 
        st.warning(f"⚠️ Attention: {nb_equipes} équipes pour {st.session_state.nb_terrains} terrains") 
        st.warning(f"Seulement {st.session_state.nb_terrains} matchs seront joués") 
    
    fp = sorted(tids, key=lambda x: (sj[x], random.random())) 
    nm, dp = [], set() 
    pr = get_current_round() + 1 
    
    for i, ea in enumerate(fp): 
        if ea in dp: 
            continue 
        for j in range(i + 1, len(fp)): 
            eb = fp[j] 
            if eb in dp: 
                continue 
            if eb not in hist[ea]: 
                nm.append({ 
                    "Round": pr,  
                    "Terrain": f"T{len(nm) + 1}",  
                    "Equipe A": ea,  
                    "Score A": 0,  
                    "Equipe B": eb,  
                    "Score B": 0 
                }) 
                dp.add(ea) 
                dp.add(eb) 
                break 
        if len(nm) >= st.session_state.nb_terrains: 
            break 
    
    # Si pas assez de matchs uniques 
    if len(nm) < st.session_state.nb_terrains and len(nm) < len(tids) // 2: 
        st.warning("⚠️ Matchs rediffusés...") 
        for i, ea in enumerate(fp): 
            if ea in dp: 
                continue 
            for j in range(i + 1, len(fp)): 
                eb = fp[j] 
                if eb in dp: 
                    continue 
                nm.append({ 
                    "Round": pr,  
                    "Terrain": f"T{len(nm) + 1}",  
                    "Equipe A": ea,  
                    "Score A": 0,  
                    "Equipe B": eb,  
                    "Score B": 0 
                }) 
                dp.add(ea) 
                dp.add(eb) 
                break 
            if len(nm) >= st.session_state.nb_terrains: 
                break 
    
    if nm: 
        # Ajouter les matchs 
        df_matchs = pd.DataFrame(nm) 
        st.session_state.matchs = pd.concat([st.session_state.matchs, df_matchs], ignore_index=True) 
        
        # Synchroniser avec matchs_detail 
        for _, m in df_matchs.iterrows(): 
            # Récupérer les détails des équipes 
            eq_a = st.session_state.equipes_fixes[st.session_state.equipes_fixes['ID'] == m['Equipe A']] 
            eq_b = st.session_state.equipes_fixes[st.session_state.equipes_fixes['ID'] == m['Equipe B']] 
            
            if not eq_a.empty and not eq_b.empty: 
                eq_a = eq_a.iloc[0] 
                eq_b = eq_b.iloc[0] 
                
                st.session_state.matchs_detail = pd.concat([ 
                    st.session_state.matchs_detail, 
                    pd.DataFrame([{ 
                        "Round": m['Round'], 
                        "Terrain": m['Terrain'], 
                        "Equipe_A_ID": m['Equipe A'], 
                        "J1_A": eq_a['J1'], 
                        "J2_A": eq_a['J2'], 
                        "Score_A": m['Score A'], 
                        "Equipe_B_ID": m['Equipe B'], 
                        "J1_B": eq_b['J1'], 
                        "J2_B": eq_b['J2'], 
                        "Score_B": m['Score B'] 
                    }]) 
                ], ignore_index=True) 
        
        st.success(f"Round {pr} généré avec {len(nm)} matchs!") 
    else: 
        st.warning("Impossible de créer des matchs") 

def generer_round_individuel_complet(): 
    """Génère un round en mode individuel avec équipes aléatoires""" 
    # Vérifier qu'on a au moins 2 joueurs 
    if len(st.session_state.joueurs) < 2: 
        st.error("Il faut au moins 2 joueurs") 
        return 
    
    # Étape 1: Créer des paires aléatoires de joueurs POUR CE ROUND 
    joueurs = [get_nom_complet(j) for j in st.session_state.joueurs]
    
    # Mélanger les joueurs 
    random.shuffle(joueurs) 
    
    # Créer les paires 
    equipes_round = [] 
    pr = get_current_round() + 1 
    
    for i in range(0, len(joueurs), 2): 
        if i + 1 < len(joueurs): 
            equipe_id = f"R{pr}_E{i//2+1}" 
            
            # Récupérer les catégories 
            cat1 = get_categorie_joueur(joueurs[i]) 
            cat2 = get_categorie_joueur(joueurs[i+1]) 
            
            equipes_round.append({ 
                "Round": pr, 
                "ID": equipe_id, 
                "Surnom": equipe_id, 
                "J1": joueurs[i], 
                "Cat1": cat1, 
                "J2": joueurs[i+1], 
                "Cat2": cat2, 
                "Coeff": round((st.session_state.categories_dict.get(cat1, 1.0) +  
                               st.session_state.categories_dict.get(cat2, 1.0)) / 2, 3) 
            }) 
        else: 
            # Joueur impair -> avec joker 
            equipe_id = f"R{pr}_E{i//2+1}" 
            cat1 = get_categorie_joueur(joueurs[i]) 
            
            equipes_round.append({ 
                "Round": pr, 
                "ID": equipe_id, 
                "Surnom": equipe_id, 
                "J1": joueurs[i], 
                "Cat1": cat1, 
                "J2": f"Joker_R{pr}", 
                "Cat2": "Joker", 
                "Coeff": round((st.session_state.categories_dict.get(cat1, 1.0) + 1.0) / 2, 3) 
            }) 
            st.warning(f"⚠️ Joueur impair: {joueurs[i]} avec Joker") 
    
    # Étape 2: Sauvegarder ces équipes dans l'historique 
    df_equipes_round = pd.DataFrame(equipes_round) 
    st.session_state.historique_equipes = pd.concat([ 
        st.session_state.historique_equipes,  
        df_equipes_round 
    ], ignore_index=True) 
    
    # Étape 3: Générer les matchs 
    nb_equipes = len(equipes_round) 
    nb_terrains = st.session_state.nb_terrains 
    
    # Vérifier si on a assez de terrains 
    matchs_possibles = min(nb_terrains, nb_equipes // 2) 
    if matchs_possibles * 2 < nb_equipes: 
        st.warning(f"⚠️ {nb_equipes} équipes pour {nb_terrains} terrains") 
        st.warning(f"Seulement {matchs_possibles} matchs ({(matchs_possibles * 4)} joueurs sur {nb_equipes * 2})") 
        
        # Proposer plusieurs créneaux horaires 
        st.info("💡 Conseil: Organisez plusieurs créneaux horaires pour ce round") 
    
    # Créer les matchs 
    matchs = [] 
    for i in range(0, min(nb_equipes, matchs_possibles * 2), 2): 
        if i + 1 < nb_equipes: 
            match = { 
                "Round": pr, 
                "Terrain": f"T{i//2 + 1}", 
                "Equipe_A_ID": equipes_round[i]["ID"], 
                "J1_A": equipes_round[i]["J1"], 
                "J2_A": equipes_round[i]["J2"], 
                "Score_A": 0, 
                "Equipe_B_ID": equipes_round[i + 1]["ID"], 
                "J1_B": equipes_round[i + 1]["J1"], 
                "J2_B": equipes_round[i + 1]["J2"], 
                "Score_B": 0 
            } 
            matchs.append(match) 
    
    # Étape 4: Ajouter les matchs 
    if matchs: 
        # Ajouter aux matchs_detail 
        df_matchs_detail = pd.DataFrame(matchs) 
        st.session_state.matchs_detail = pd.concat([ 
            st.session_state.matchs_detail,  
            df_matchs_detail 
        ], ignore_index=True) 
        
        # Synchroniser avec l'ancien format pour compatibilité 
        df_matchs_compat = pd.DataFrame([{ 
            "Round": m["Round"], 
            "Terrain": m["Terrain"], 
            "Equipe A": m["Equipe_A_ID"], 
            "Score A": m["Score_A"], 
            "Equipe B": m["Equipe_B_ID"], 
            "Score B": m["Score_B"] 
        } for m in matchs]) 
        
        st.session_state.matchs = pd.concat([ 
            st.session_state.matchs, 
            df_matchs_compat 
        ], ignore_index=True) 
        
        st.success(f"✅ Round {pr} généré avec {len(matchs)} matchs!") 
        st.info(f"🎯 Mode Individuel: {len(equipes_round)} équipes créées pour ce round") 
        
        # Afficher un récapitulatif 
        with st.expander("📊 Détail des équipes de ce round"): 
            st.dataframe(df_equipes_round.drop(columns=["Round"]), use_container_width=True) 
    else: 
        st.warning("Impossible de créer des matchs") 

def reinitialiser_matchs(): 
    st.session_state.matchs = pd.DataFrame(columns=["Round", "Terrain", "Equipe A", "Score A", "Equipe B", "Score B"]) 
    st.session_state.matchs_detail = pd.DataFrame(columns=[ 
        "Round", "Terrain",  
        "Equipe_A_ID", "J1_A", "J2_A", "Score_A", 
        "Equipe_B_ID", "J1_B", "J2_B", "Score_B" 
    ]) 
    st.session_state.confirm_reset_matchs = False 
    st.success("✅ Matchs réinitialisés!") 

def reinitialiser_tournoi(): 
    for k in list(st.session_state.keys()): 
        if k!='profil': 
            del st.session_state[k] 
    # Réinitialiser avec les nouvelles structures 
    for key, val in defaults.items(): 
        if key not in st.session_state: 
            st.session_state[key] = val 
    st.session_state.confirm_reset_tournoi = False 
    st.success("✅ Tournoi complètement réinitialisé!") 
    
# === INITIALISATION SESSION STATE === 
# S'assurer que toutes les clés par défaut sont initialisées 
for key, val in defaults.items(): 
    if key not in st.session_state: 
        st.session_state[key] = val 
        
# === INTERFACE === 
set_background(st.session_state.bg_image_data) 
st.title(f"🏸 {st.session_state.nom_tournoi}") 

# SIDEBAR 
with st.sidebar: 
    st.header("👤 Profil") 
    pa = st.radio("Profil:", ["Joueur", "Organisateur"], index=0 if st.session_state.profil=="Joueur" else 1, key="profil_radio") 
    if pa=="Organisateur" and st.session_state.profil=="Joueur": 
        mdp = st.text_input("Mot de passe:", type="password", key="mdp_input") 
        if st.button("🔓 Valider", key="valider_mdp"): 
            if mdp.upper()==MOT_DE_PASSE_ORGANISATEUR: 
                st.session_state.profil = "Organisateur" 
                st.success("✅ Mode Organisateur!") 
                st.rerun() 
            else: 
                st.error("❌ Incorrect!") 
    elif pa=="Joueur" and st.session_state.profil=="Organisateur": 
        st.session_state.profil = "Joueur" 
        st.rerun() 
    st.divider() 
    st.info("🎮 **Mode Joueur**" if st.session_state.profil=="Joueur" else "👑 **Mode Organisateur**") 
    
    # Indicateur du mode tournoi 
    st.divider() 
    if st.session_state.mode_tournoi == "Classique": 
        st.success("🏆 **Mode Classique**") 
        st.caption("Équipes fixes, classement par équipe valide") 
    else: 
        st.warning("🎯 **Mode Individuel**") 
        st.caption("Équipes aléatoires à chaque round") 

# MODIFICATION DES ONGLETS 
tabs = st.tabs(["👥 Joueurs", "🤝 Équipes", "🏸 Matchs", "🏆 Classement Équipes", "👤 Classement Individuel"] + (["⚙️ Paramètres"] if est_organisateur() else [])) 

# ONGLET JOUEURS 
with tabs[0]: 
    st.subheader("Saisie des joueurs") 
    if st.session_state.erreur_saisie: 
        st.error(st.session_state.erreur_saisie) 
    c1, c2, c3, c4 = st.columns([2, 2, 3, 1]) 
    with c1: 
        np = st.text_input("Prénom", key="ip") 
    with c2: 
        nn = st.text_input("Nom", key="in") 
    with c3: 
        nc = st.selectbox("Catégorie", [c for c in st.session_state.categories_dict if c!="Joker"], key="ic") 
    with c4: 
        st.write("") 
        st.write("") 
        if st.button("➕ Ajouter", key="ajouter_joueur"): 
            pc, nc_clean = np.strip(), nn.strip() 
            if not pc or not nc_clean: 
                st.session_state.erreur_saisie = "⚠️ Prénom ET nom requis!" 
                st.rerun() 
            elif joueur_existe(pc, nc_clean): 
                st.session_state.erreur_saisie = f"⚠️ {pc} {nc_clean} existe déjà!" 
                st.rerun() 
            elif any(j['Prénom'].lower().strip()==pc.lower() and j['Nom'].lower().strip()==nc_clean.lower() for j in st.session_state.temp_joueurs): 
                st.session_state.erreur_saisie = f"⚠️ {pc} {nc_clean} en attente!" 
                st.rerun() 
            else: 
                st.session_state.temp_joueurs.append({"Prénom": pc, "Nom": nc_clean, "Catégorie": nc}) 
                st.session_state.erreur_saisie = None 
                st.rerun() 
    
    if st.session_state.temp_joueurs: 
        st.subheader("Joueurs à valider") 
        if not est_organisateur(): 
            st.info("👑 Validation réservée à l'organisateur") 
        if est_organisateur(): 
            cg1, cg2 = st.columns(2) 
            with cg1: 
                if st.button("✅ Valider TOUS", use_container_width=True, key="valider_tous"): 
                    for j in st.session_state.temp_joueurs: 
                        if not joueur_existe(j["Prénom"], j["Nom"]): 
                            st.session_state.joueurs.append(j) 
                    st.session_state.temp_joueurs = [] 
                    st.session_state.erreur_saisie = None 
                    st.rerun() 
            with cg2: 
                if st.button("🗑️ Supprimer TOUS", use_container_width=True, key="supprimer_tous"): 
                    st.session_state.temp_joueurs = [] 
                    st.session_state.erreur_saisie = None 
                    st.rerun() 
        st.divider() 
        for idx, j in enumerate(st.session_state.temp_joueurs): 
            c1, c2, c3, c4, c5 = st.columns([1, 2, 2, 3, 2]) 
            with c1: 
                st.write(f"**{len(st.session_state.joueurs)+idx+1}**") 
            with c2: 
                st.write(j["Prénom"]) 
            with c3: 
                st.write(j["Nom"]) 
            with c4: 
                st.write(j["Catégorie"]) 
            with c5: 
                cv, cs = st.columns(2) 
                with cv: 
                    if st.button("✅", key=f"v{idx}", disabled=not est_organisateur()): 
                        if not j["Prénom"].strip() or not j["Nom"].strip(): 
                            st.session_state.erreur_saisie = "Prénom/Nom vides" 
                            st.rerun() 
                        elif joueur_existe(j["Prénom"], j["Nom"]): 
                            st.session_state.erreur_saisie = f"{j['Prénom']} {j['Nom']} existe!" 
                            st.rerun() 
                        else: 
                            st.session_state.joueurs.append(j) 
                            st.session_state.temp_joueurs.pop(idx) 
                            st.session_state.erreur_saisie = None 
                            st.rerun() 
                with cs: 
                    if st.button("🗑️", key=f"dt{idx}", disabled=not est_organisateur()): 
                        st.session_state.temp_joueurs.pop(idx) 
                        st.session_state.erreur_saisie = None 
                        st.rerun() 
        st.divider() 
    
    st.subheader("Liste des inscrits") 
    if st.session_state.joueurs: 
        for idx, j in enumerate(st.session_state.joueurs, 1): 
            c1, c2, c3, c4, c5 = st.columns([1, 2, 2, 3, 1]) 
            with c1: 
                st.write(f"**{idx}**") 
            with c2: 
                st.write(j["Prénom"]) 
            with c3: 
                st.write(j["Nom"]) 
            with c4: 
                st.write(j["Catégorie"]) 
            with c5: 
                if st.button("🗑️", key=f"dj{idx}", disabled=not est_organisateur()): 
                    st.session_state.joueurs.pop(idx-1) 
                    st.rerun() 
    else: 
        st.info("Aucun joueur inscrit") 
    
    st.divider() 
    
    if est_organisateur(): 
        ci1, ci2 = st.columns(2) 
        with ci1: 
            st.subheader("📥 Importer joueurs") 
            uj = st.file_uploader("CSV (Prénom,Nom,Catégorie)", type=['csv'], key="ij") 
            if uj and st.button("Charger", key="bij"): 
                try: 
                    df = pd.read_csv(uj) 
                    if all(c in df.columns for c in ['Prénom', 'Nom', 'Catégorie']): 
                        cnt = 0 
                        for _, r in df.iterrows(): 
                            if not joueur_existe(r['Prénom'], r['Nom']) and r['Catégorie']!="Joker": 
                                st.session_state.joueurs.append({'Prénom': r['Prénom'], 'Nom': r['Nom'], 'Catégorie': r['Catégorie']}) 
                                cnt += 1 
                        st.success(f"✅ {cnt} joueurs importés!") 
                        st.rerun() 
                    else: 
                        st.error("Colonnes requises: Prénom, Nom, Catégorie") 
                except Exception as e: 
                    st.error(f"Erreur: {e}") 
        with ci2: 
            st.subheader("📤 Exporter joueurs") 
            if st.session_state.joueurs: 
                csv = pd.DataFrame(st.session_state.joueurs).to_csv(index=False).encode('utf-8') 
                st.download_button("💾 Télécharger CSV", csv, "joueurs.csv", "text/csv", key="exporter_joueurs") 
    
    st.divider() 
    c1, c2 = st.columns(2) 
    with c1: 
        if st.session_state.mode_tournoi == "Classique": 
            if st.button("🔥 GÉNÉRER LES ÉQUIPES", use_container_width=True, disabled=not est_organisateur(), key="generer_equipes_classique"): 
                generer_paires_equilibrees("nouveau") 
                st.rerun() 
        else:  # Mode Individuel 
            if st.button("🎲 GÉNÉRER ÉQUIPES ALÉATOIRES", use_container_width=True, disabled=not est_organisateur(), key="generer_equipes_aleatoires"): 
                generer_equipes_aleatoires_mode_individuel() 
                st.rerun() 
    with c2: 
        if st.session_state.mode_tournoi == "Classique": 
            jna = [j for j in st.session_state.joueurs if not joueur_dans_equipe(j['Prénom'], j['Nom']) and j['Catégorie']!="Joker"] 
            if len(jna)>=1: 
                if st.button("➕ AJOUTER DES ÉQUIPES", use_container_width=True, disabled=not est_organisateur(), key="ajouter_equipes_classique"): 
                    generer_paires_equilibrees("ajouter") 
                    st.rerun() 
            else: 
                st.button("➕ AJOUTER DES ÉQUIPES", use_container_width=True, disabled=True, help="Il faut au moins 1 joueur non affecté", key="ajouter_equipes_disabled") 
        else:  # Mode Individuel 
            st.button("➕ AJOUTER DES ÉQUIPES", use_container_width=True, disabled=True,  
                     help="En mode Individuel, toutes les équipes sont regénérées à chaque round", key="ajouter_equipes_individuel") 

# ONGLET ÉQUIPES 
with tabs[1]: 
    st.subheader("Paires constituées") 
    
    # SECTION AFFICHAGE DES ÉQUIPES 
    if st.session_state.mode_tournoi == "Classique": 
        # Mode Classique : afficher équipes_fixes 
        if not st.session_state.equipes_fixes.empty: 
            if est_organisateur(): 
                df_display = st.session_state.equipes_fixes.copy() 
                edited_df = st.data_editor( 
                    df_display, 
                    use_container_width=True, 
                    column_config={ 
                        "ID": st.column_config.TextColumn(disabled=True), 
                        "Surnom": st.column_config.TextColumn("Surnom", help="Modifiable"), 
                        "J1": st.column_config.TextColumn(disabled=True), 
                        "Cat1": st.column_config.TextColumn(disabled=True), 
                        "J2": st.column_config.TextColumn(disabled=True), 
                        "Cat2": st.column_config.TextColumn(disabled=True), 
                        "Coeff": st.column_config.NumberColumn(disabled=True), 
                    }, 
                    hide_index=True, 
                    key="edit_equipes_fixes" 
                ) 
                
                # Vérifier les doublons de surnoms 
                for idx, row in edited_df.iterrows(): 
                    nouveau_surnom = row['Surnom'] 
                    if surnom_existe_deja(nouveau_surnom, row['ID']): 
                        st.error(f"❌ Le nom d'équipe '{nouveau_surnom}' est déjà pris par une autre équipe!") 
                    else: 
                        st.session_state.equipes_fixes.at[idx, 'Surnom'] = nouveau_surnom 
                
                # Boutons de suppression 
                st.divider() 
                st.subheader("🗑️ Supprimer des équipes") 
                for idx, eq in st.session_state.equipes_fixes.iterrows(): 
                    col1, col2 = st.columns([4, 1]) 
                    with col1: 
                        st.write(f"**{eq['ID']}** ({get_nom_affichage_equipe(eq)}): {eq['J1']} & {eq['J2']}") 
                    with col2: 
                        if equipe_dans_matchs(eq['ID']): 
                            st.button("🗑️", key=f"del_eq_{idx}", disabled=True, help="Équipe déjà dans un round") 
                        else: 
                            if st.button("🗑️", key=f"del_eq_{idx}"): 
                                st.session_state.equipes_fixes = st.session_state.equipes_fixes.drop(idx).reset_index(drop=True) 
                                st.success(f"✅ Équipe {eq['ID']} supprimée!") 
                                st.rerun() 
            else: 
                st.dataframe(st.session_state.equipes_fixes, use_container_width=True, hide_index=True) 
        else: 
            st.info("💡 Aucune équipe fixe n'a encore été créée.") 
    else: 
        # Mode Individuel : afficher équipes du round actuel 
        st.info("🎯 **Mode Tournoi Individuel**: Les équipes sont générées aléatoirement à chaque round.") 
        
        equipes_actuelles = get_equipes_actuelles() 
        
        if not equipes_actuelles.empty: 
            st.subheader(f"Équipes du Round {get_current_round()}") 
            st.dataframe(equipes_actuelles, use_container_width=True, hide_index=True) 
            
            # Historique des équipes 
            with st.expander("📜 Voir l'historique des équipes par round"): 
                if not st.session_state.historique_equipes.empty: 
                    for round_num in sorted(st.session_state.historique_equipes["Round"].unique()): 
                        st.write(f"**Round {round_num}**") 
                        df_round = st.session_state.historique_equipes[ 
                            st.session_state.historique_equipes["Round"] == round_num 
                        ].drop(columns=["Round"]) 
                        st.dataframe(df_round, use_container_width=True, hide_index=True) 
        else: 
            st.info("💡 Aucun round n'a encore été généré. Créez un premier round dans l'onglet Matchs.") 
    
    # SECTION EXPORTATION 
    if est_organisateur(): 
        st.divider() 
        st.subheader("📤 Exporter les équipes") 
        
        if st.session_state.mode_tournoi == "Classique": 
            if not st.session_state.equipes_fixes.empty: 
                col_exp1, col_exp2 = st.columns(2) 
                
                with col_exp1: 
                    csv = st.session_state.equipes_fixes.to_csv(index=False).encode('utf-8') 
                    st.download_button( 
                        "💾 Télécharger CSV",  
                        csv,  
                        f"equipes_{st.session_state.nom_tournoi}.csv",  
                        "text/csv", 
                        use_container_width=True, 
                        key="exporter_equipes_csv"
                    ) 
                
                with col_exp2: 
                    pdf = generer_pdf_equipes() 
                    fname = f"equipes_{st.session_state.nom_tournoi}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf" 
                    st.download_button( 
                        "📄 Télécharger PDF",  
                        pdf,  
                        fname,  
                        "application/pdf", 
                        use_container_width=True,
                        key="exporter_equipes_pdf"
                    ) 
        else: 
            # Mode Individuel : exporter l'historique 
            if not st.session_state.historique_equipes.empty: 
                col_exp1, col_exp2 = st.columns(2) 
                
                with col_exp1: 
                    csv = st.session_state.historique_equipes.to_csv(index=False).encode('utf-8') 
                    st.download_button( 
                        "💾 Historique CSV",  
                        csv,  
                        f"historique_equipes_{st.session_state.nom_tournoi}.csv",  
                        "text/csv", 
                        use_container_width=True,
                        key="exporter_historique_csv"
                    ) 
                
                with col_exp2: 
                    equipes_actuelles = get_equipes_actuelles() 
                    if not equipes_actuelles.empty: 
                        csv_actuelles = equipes_actuelles.to_csv(index=False).encode('utf-8') 
                        st.download_button( 
                            "💾 Équipes actuelles CSV",  
                            csv_actuelles,  
                            f"equipes_round_{get_current_round()}_{st.session_state.nom_tournoi}.csv",  
                            "text/csv", 
                            use_container_width=True,
                            key="exporter_equipes_actuelles_csv"
                        ) 
    
    # SECTION IMPORTATION (unique - corrigé le problème de clé dupliquée)
    if est_organisateur():
        st.divider()
        st.subheader("📥 Importer des équipes")
        
        if st.session_state.mode_tournoi == "Classique":
            if len(st.session_state.joueurs) > 0:
                ue = st.file_uploader("Télécharger un fichier CSV d'équipes", type=['csv'], key="ie_uploader_unique")
                if ue and st.button("Charger les équipes", key="btn_import_equipes_unique", type="primary"):
                    try:
                        df = pd.read_csv(ue)
                        required = ['ID', 'Surnom', 'J1', 'Cat1', 'J2', 'Cat2', 'Coeff']
                        if all(c in df.columns for c in required):
                            # Vérifier que tous les joueurs existent
                            erreur_import = False
                            for _, row in df.iterrows():
                                if not est_joker(row['J1']):
                                    parts = row['J1'].strip().split(' ', 1)
                                    if len(parts) < 2 or not joueur_existe(parts[0], parts[1]):
                                        st.error(f"❌ Joueur '{row['J1']}' non trouvé dans la liste!")
                                        erreur_import = True
                                        break
                                if not est_joker(row['J2']):
                                    parts = row['J2'].strip().split(' ', 1)
                                    if len(parts) < 2 or not joueur_existe(parts[0], parts[1]):
                                        st.error(f"❌ Joueur '{row['J2']}' non trouvé dans la liste!")
                                        erreur_import = True
                                        break
                            
                            if not erreur_import:
                                if st.session_state.equipes_fixes.empty:
                                    st.session_state.equipes_fixes = df
                                else:
                                    st.session_state.equipes_fixes = pd.concat([st.session_state.equipes_fixes, df], ignore_index=True)
                                st.success(f"✅ {len(df)} équipes importées!")
                                st.rerun()
                        else:
                            st.error("❌ Colonnes manquantes! Format requis: ID, Surnom, J1, Cat1, J2, Cat2, Coeff")
                    except Exception as e:
                        st.error(f"❌ Erreur: {e}")
            else:
                st.warning("⚠️ Vous devez d'abord ajouter des joueurs avant de pouvoir importer des équipes.")
        else:
            st.info("📋 En mode individuel, les équipes sont générées automatiquement à chaque round.")

# ONGLET MATCHS 
with tabs[2]: 
    # Création des colonnes POUR LE BOUTON SEULEMENT 
    col_a, col_b = st.columns([1, 1]) 
    
    with col_a: 
        disabled_btn = not est_organisateur() 
        
        if st.session_state.mode_tournoi == "Individuel": 
            # Vérifier qu'on a au moins 2 joueurs 
            if len(st.session_state.joueurs) < 2: 
                disabled_btn = True 
                st.warning("⚠️ Il faut au moins 2 joueurs") 
        else: 
            # Mode Classique : vérifier qu'on a au moins 2 équipes 
            if len(st.session_state.equipes_fixes) < 2: 
                disabled_btn = True 
                st.warning("⚠️ Il faut au moins 2 équipes") 
        
        if st.button("🎲 Lancer un nouveau round", disabled=disabled_btn, use_container_width=True, key="lancer_round"): 
            generer_round_equitable() 
            st.rerun() 
    
    # Afficher des informations spécifiques au mode 
    if st.session_state.mode_tournoi == "Individuel": 
        st.info("🎯 **Mode Individuel**: Les équipes sont regénérées aléatoirement à chaque round.") 
        if len(st.session_state.joueurs) >= 2: 
            st.write(f"**{len(st.session_state.joueurs)} joueurs** → {len(st.session_state.joueurs) // 2} équipes possibles") 
    
    st.write(f"**Round actuel: {get_current_round()}**") 
        
    # SECTION AFFICHAGE DES MATCHS (en premier) 
    if not st.session_state.matchs.empty: 
        # Pour l'affichage, on utilise matchs_detail si disponible, sinon matchs (pour compatibilité) 
        if st.session_state.mode_tournoi == "Individuel" and not st.session_state.matchs_detail.empty: 
            # Afficher les matchs avec les noms des joueurs 
            matchs_display = st.session_state.matchs_detail.copy() 
            
            # Ajouter les surnoms si possible 
            for idx, row in matchs_display.iterrows(): 
                # Récupérer les équipes du round correspondant 
                round_num = row['Round'] 
                equipes_round = get_equipes_par_round(round_num) 
                
                if not equipes_round.empty: 
                    # Équipe A 
                    eq_a = equipes_round[equipes_round['ID'] == row['Equipe_A_ID']] 
                    if not eq_a.empty: 
                        matchs_display.at[idx, 'Equipe_A_ID'] = get_nom_affichage_equipe(eq_a.iloc[0]) 
                    
                    # Équipe B 
                    eq_b = equipes_round[equipes_round['ID'] == row['Equipe_B_ID']] 
                    if not eq_b.empty: 
                        matchs_display.at[idx, 'Equipe_B_ID'] = get_nom_affichage_equipe(eq_b.iloc[0]) 
            
            # Renommer les colonnes pour l'affichage - CORRECTION ICI
            matchs_display = matchs_display.rename(columns={ 
                'Equipe_A_ID': 'Équipe A', 
                'J1_A': 'Joueur 1A', 
                'J2_A': 'Joueur 2A', 
                'Score_A': 'Score A',  # CORRECTION AJOUTÉE
                'Score_B': 'Score B',  # CORRECTION AJOUTÉE
                'Equipe_B_ID': 'Équipe B', 
                'J1_B': 'Joueur 1B', 
                'J2_B': 'Joueur 2B' 
            }) 
            
            # Sélectionner les colonnes à afficher 
            cols_affichage = ['Round', 'Terrain', 'Équipe A', 'Joueur 1A', 'Joueur 2A', 'Score A', 'Score B', 'Équipe B', 'Joueur 1B', 'Joueur 2B'] 
            # Vérifier que toutes les colonnes existent
            cols_existantes = [col for col in cols_affichage if col in matchs_display.columns]
            matchs_display = matchs_display[cols_existantes]
        else: 
            # Mode classique ou pas de matchs_detail : afficher les matchs avec surnoms 
            matchs_display = st.session_state.matchs.copy() 
            for idx, row in matchs_display.iterrows(): 
                if st.session_state.mode_tournoi == "Classique": 
                    eq_a = st.session_state.equipes_fixes[st.session_state.equipes_fixes['ID'] == row['Equipe A']] 
                    eq_b = st.session_state.equipes_fixes[st.session_state.equipes_fixes['ID'] == row['Equipe B']] 
                else: 
                    # Mode individuel mais matchs_detail vide, on essaie de récupérer les équipes du round 
                    round_num = row['Round'] 
                    equipes_round = get_equipes_par_round(round_num) 
                    eq_a = equipes_round[equipes_round['ID'] == row['Equipe A']] if not equipes_round.empty else pd.DataFrame() 
                    eq_b = equipes_round[equipes_round['ID'] == row['Equipe B']] if not equipes_round.empty else pd.DataFrame() 
                
                if not eq_a.empty: 
                    matchs_display.at[idx, 'Equipe A'] = get_nom_affichage_equipe(eq_a.iloc[0]) 
                if not eq_b.empty: 
                    matchs_display.at[idx, 'Equipe B'] = get_nom_affichage_equipe(eq_b.iloc[0]) 
        
        if est_organisateur(): 
            # Éditeur de données 
            if st.session_state.mode_tournoi == "Individuel" and not st.session_state.matchs_detail.empty: 
                # Pour le mode individuel, on édite les scores dans matchs_detail 
                edited_df = st.data_editor( 
                    matchs_display, 
                    use_container_width=True, 
                    column_config={ 
                        "Round": st.column_config.NumberColumn(disabled=True), 
                        "Terrain": st.column_config.TextColumn(disabled=True), 
                        "Équipe A": st.column_config.TextColumn(disabled=True), 
                        "Joueur 1A": st.column_config.TextColumn(disabled=True), 
                        "Joueur 2A": st.column_config.TextColumn(disabled=True), 
                        "Équipe B": st.column_config.TextColumn(disabled=True), 
                        "Joueur 1B": st.column_config.TextColumn(disabled=True), 
                        "Joueur 2B": st.column_config.TextColumn(disabled=True), 
                    }, 
                    hide_index=True, 
                    key="edit_matchs_detail" 
                ) 
                # Mettre à jour les scores dans matchs_detail et matchs 
                for idx, row in edited_df.iterrows(): 
                    st.session_state.matchs_detail.at[idx, 'Score_A'] = row['Score A'] 
                    st.session_state.matchs_detail.at[idx, 'Score_B'] = row['Score B'] 
                    # Mettre à jour matchs aussi (pour compatibilité) 
                    match_idx = st.session_state.matchs[ 
                        (st.session_state.matchs['Round'] == row['Round']) &  
                        (st.session_state.matchs['Terrain'] == row['Terrain']) 
                    ].index 
                    if len(match_idx) > 0: 
                        st.session_state.matchs.at[match_idx[0], 'Score A'] = row['Score A'] 
                        st.session_state.matchs.at[match_idx[0], 'Score B'] = row['Score B'] 
            else: 
                # Mode classique 
                matchs_edited = st.data_editor( 
                    matchs_display, 
                    use_container_width=True, 
                    column_config={ 
                        "Round": st.column_config.NumberColumn(disabled=True), 
                        "Terrain": st.column_config.TextColumn(disabled=True), 
                        "Equipe A": st.column_config.TextColumn(disabled=True), 
                        "Equipe B": st.column_config.TextColumn(disabled=True), 
                    }, 
                    hide_index=True, 
                    key="edit_matchs" 
                ) 
                # Synchroniser scores 
                st.session_state.matchs['Score A'] = matchs_edited['Score A'] 
                st.session_state.matchs['Score B'] = matchs_edited['Score B'] 
                
                # Mettre à jour matchs_detail si on est en mode classique 
                if st.session_state.mode_tournoi == "Classique": 
                    for idx, row in st.session_state.matchs.iterrows(): 
                        # Trouver le match correspondant dans matchs_detail 
                        mask = ( 
                            (st.session_state.matchs_detail['Round'] == row['Round']) & 
                            (st.session_state.matchs_detail['Terrain'] == row['Terrain']) & 
                            (st.session_state.matchs_detail['Equipe_A_ID'] == row['Equipe A']) & 
                            (st.session_state.matchs_detail['Equipe_B_ID'] == row['Equipe B']) 
                        ) 
                        if mask.any(): 
                            detail_idx = st.session_state.matchs_detail[mask].index[0] 
                            st.session_state.matchs_detail.at[detail_idx, 'Score_A'] = row['Score A'] 
                            st.session_state.matchs_detail.at[detail_idx, 'Score_B'] = row['Score B'] 
        else: 
            st.dataframe(matchs_display, use_container_width=True, hide_index=True) 
            
        # SECTION EXPORTATION (uniquement si matchs existent) 
        if est_organisateur() and not st.session_state.matchs.empty: 
            st.divider() 
            st.subheader("📤 Exporter les matchs") 
            
            # Créer 4 colonnes 
            col_exp1, col_exp2, col_exp3, col_exp4 = st.columns(4) 
            
            with col_exp1: 
                # Export CSV simple (format original) 
                csv_simple = st.session_state.matchs.to_csv(index=False).encode('utf-8') 
                st.download_button( 
                    "💾 CSV Simple",  
                    csv_simple,  
                    f"matchs_{st.session_state.nom_tournoi}.csv",  
                    "text/csv", 
                    use_container_width=True, 
                    help="Format simple avec équipes et scores",
                    key="exporter_matchs_csv"
                ) 
            
            with col_exp2: 
                # Export CSV détaillé (avec joueurs) - seulement si matchs_detail n'est pas vide 
                if not st.session_state.matchs_detail.empty: 
                    csv_detaille = exporter_matchs_detail_csv() 
                    if csv_detaille: 
                        fname = f"matchs_detaille_{st.session_state.nom_tournoi}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv" 
                        st.download_button( 
                            "📊 CSV Détail",  
                            csv_detaille,  
                            fname,  
                            "text/csv", 
                            use_container_width=True, 
                            help="Format détaillé avec noms des joueurs",
                            key="exporter_matchs_detail_csv"
                        ) 
                else: 
                    st.button("📊 CSV Détail", disabled=True, use_container_width=True,  
                             help="Aucun détail de match disponible", key="exporter_matchs_detail_disabled") 
            
            with col_exp3: 
                # Export XLSX détaillé 
                if not st.session_state.matchs_detail.empty: 
                    xlsx_data = exporter_matchs_detail_xlsx() 
                    if xlsx_data: 
                        fname = f"matchs_{st.session_state.nom_tournoi}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx" 
                        st.download_button( 
                            "📗 Excel XLSX",  
                            xlsx_data,  
                            fname,  
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                            use_container_width=True, 
                            help="Format Excel avec noms des joueurs",
                            key="exporter_matchs_xlsx"
                        ) 
                else: 
                    st.button("📗 Excel XLSX", disabled=True, use_container_width=True, 
                             help="Aucun détail de match disponible", key="exporter_matchs_xlsx_disabled") 
            
            with col_exp4: 
                # Export PDF 
                if not st.session_state.matchs_detail.empty: 
                    pdf = generer_pdf_rounds_detail() 
                    fname = f"rounds_{st.session_state.nom_tournoi}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf" 
                    st.download_button( 
                        "📄 PDF Détail",  
                        pdf,  
                        fname,  
                        "application/pdf", 
                        use_container_width=True, 
                        help="PDF avec noms des joueurs",
                        key="exporter_matchs_pdf_detail"
                    ) 
                else: 
                    # PDF simple (ancien format) 
                    pdf = generer_pdf_rounds() 
                    fname = f"rounds_{st.session_state.nom_tournoi}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf" 
                    st.download_button( 
                        "📄 PDF Simple",  
                        pdf,  
                        fname,  
                        "application/pdf", 
                        use_container_width=True, 
                        help="PDF simple",
                        key="exporter_matchs_pdf_simple"
                    ) 

    # SECTION IMPORTATION (en bas, après l'affichage) 
    if est_organisateur() and st.session_state.mode_tournoi == "Classique" and len(st.session_state.equipes_fixes) >= 2: 
        st.subheader("📥 Importer des matchs") 
        um = st.file_uploader("Télécharger un fichier CSV de matchs", type=['csv'], key="im_uploader_unique") 
        if um and st.button("Charger les matchs", key="btn_import_matchs_unique", type="primary"): 
            try: 
                df = pd.read_csv(um) 
                required = ['Round', 'Terrain', 'Equipe A', 'Score A', 'Equipe B', 'Score B'] 
                if all(c in df.columns for c in required): 
                    # Vérifier que toutes les équipes existent 
                    erreur_import = False 
                    for _, row in df.iterrows(): 
                        if row['Equipe A'] not in st.session_state.equipes_fixes['ID'].values: 
                            st.error(f"❌ Équipe '{row['Equipe A']}' non trouvée!") 
                            erreur_import = True 
                            break 
                        if row['Equipe B'] not in st.session_state.equipes_fixes['ID'].values: 
                            st.error(f"❌ Équipe '{row['Equipe B']}' non trouvée!") 
                            erreur_import = True 
                            break 
                    
                    if not erreur_import: 
                        # Demander confirmation si des matchs existent déjà 
                        if not st.session_state.matchs.empty: 
                            st.session_state.pending_matchs_import = df 
                            st.session_state.confirm_import_matchs = True 
                            st.rerun() 
                        else: 
                            st.session_state.matchs = df 
                            st.success(f"✅ {len(df)} matchs importés!") 
                            st.rerun() 
                else: 
                    st.error("❌ Colonnes manquantes! Format requis: Round, Terrain, Equipe A, Score A, Equipe B, Score B") 
            except Exception as e: 
                st.error(f"❌ Erreur: {e}") 
    elif est_organisateur() and st.session_state.mode_tournoi == "Classique" and len(st.session_state.equipes_fixes) < 2: 
        st.warning("⚠️ Vous devez d'abord créer au moins 2 équipes dans l'onglet Équipes avant de pouvoir importer des matchs.") 
    
    # Gestion de la confirmation d'import (si nécessaire) 
    if st.session_state.confirm_import_matchs and st.session_state.pending_matchs_import is not None: 
        st.divider() 
        st.warning("⚠️ Attention : Cet import va remplacer TOUS les matchs existants !") 
        st.info(f"Matchs actuels : {len(st.session_state.matchs)} | Matchs à importer : {len(st.session_state.pending_matchs_import)}") 
        col_conf1, col_conf2 = st.columns(2) 
        with col_conf1: 
            if st.button("✅ Confirmer l'import", type="primary", use_container_width=True, key="confirmer_import_matchs"): 
                st.session_state.matchs = st.session_state.pending_matchs_import 
                st.session_state.confirm_import_matchs = False 
                st.session_state.pending_matchs_import = None 
                st.success("✅ Matchs importés avec succès!") 
                st.rerun() 
        with col_conf2: 
            if st.button("❌ Annuler l'import", use_container_width=True, key="annuler_import_matchs"): 
                st.session_state.confirm_import_matchs = False 
                st.session_state.pending_matchs_import = None 
                st.rerun() 

# ONGLET CLASSEMENT ÉQUIPES 
with tabs[3]: 
    st.header(f"Classement Général - Mode {st.session_state.algo_classement}") 
    
    if st.session_state.mode_tournoi == "Individuel": 
        st.warning("⚠️ **Mode Tournoi Individuel**: Le classement par équipe n'a pas de sens car les équipes changent à chaque round. Consultez le classement individuel.") 
        # On ne calcule pas le classement par équipe en mode individuel
        stats = []
    else:
        # Mode Classique : on calcule le classement normal
        if not st.session_state.matchs.empty: 
            stats = [] 
            # CORRECTION ICI : utiliser equipes_fixes au lieu de equipes
            for _, eq in st.session_state.equipes_fixes.iterrows(): 
                eid = eq["ID"] 
                m_eq = st.session_state.matchs[(st.session_state.matchs["Equipe A"]==eid)|(st.session_state.matchs["Equipe B"]==eid)] 
                pm, pe, v, n, d = 0, 0, 0, 0, 0 
                for _, m in m_eq.iterrows(): 
                    if m["Score A"]==0 and m["Score B"]==0: 
                        continue 
                    is_a = m["Equipe A"]==eid 
                    ma, sa = (m["Score A"], m["Score B"]) if is_a else (m["Score B"], m["Score A"]) 
                    pm += ma 
                    pe += sa 
                    if ma>sa: 
                        v+=1 
                    elif ma==sa: 
                        n+=1 
                    else: 
                        d+=1 
                diff = pm - pe 
                if st.session_state.algo_classement=="Pondéré": 
                    score = round(((v*3)+(n*1))*eq["Coeff"], 2) 
                else: 
                    score = (v*2)+(n*1) 
                stats.append({ 
                    "Équipe": get_nom_affichage_equipe(eq), 
                    "Joueurs": f"{eq['J1']} & {eq['J2']}", 
                    "V": v, "N": n, "D": d, "Diff": diff, "Points": score 
                }) 
        else: 
            stats = []
    
    if stats:  # CORRECTION : vérifier que stats n'est pas vide
        df_classement = pd.DataFrame(stats).sort_values(by=["Points", "Diff"], ascending=False) 
        df_classement.index = range(1, len(df_classement)+1) 
        st.dataframe(df_classement, use_container_width=True) 
        
        st.divider() 
        st.subheader("📤 Exporter le classement") 
        c1, c2, c3 = st.columns(3) 
        
        with c1: 
            excel_data = generer_excel_classement() 
            if excel_data: 
                fname = f"classement_{st.session_state.nom_tournoi}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx" 
                st.download_button("📊 Excel (XLSX)", excel_data, fname, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, key="exporter_classement_equipes_xlsx")  # CHANGEMENT DE CLÉ ICI
        
        with c2: 
            pdf_data = generer_pdf_classement() 
            fname = f"classement_{st.session_state.nom_tournoi}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf" 
            st.download_button("📄 PDF", pdf_data, fname, "application/pdf", use_container_width=True, key="exporter_classement_equipes_pdf")  # CHANGEMENT DE CLÉ ICI
    else: 
        if st.session_state.mode_tournoi != "Individuel":  # Ne pas afficher ce message en mode individuel
            st.info("Aucun match joué pour le moment")
          
 # ONGLET CLASSEMENT INDIVIDUEL 
with tabs[4]: 
    st.header("👤 Classement Individuel") 
    
    # Avertissement pour le mode tournoi individuel 
    if st.session_state.mode_tournoi == "Individuel": 
        st.success("🏆 **Mode Tournoi Individuel**: Les équipes changent à chaque round, seul ce classement a du sens.") 
    
    # Calculer le classement 
    df_classement_individuel = calculer_classement_individuel() 
    
    if not df_classement_individuel.empty: 
        # Affichage 
        st.subheader(f"Classement - {st.session_state.algo_classement_individuel}") 
        st.dataframe(df_classement_individuel, use_container_width=True) 
        
        # Exportation 
        st.divider() 
        st.subheader("📤 Exporter le classement") 
        
        col_exp1, col_exp2, col_exp3 = st.columns(3) 
        
        with col_exp1: 
            # Export CSV 
            csv_data = df_classement_individuel.to_csv(index=True).encode('utf-8') 
            fname = f"classement_individuel_{datetime.now().strftime('%Y%m%d_%H%M')}.csv" 
            st.download_button("💾 CSV", csv_data, fname, "text/csv", use_container_width=True, key="exporter_classement_individuel_csv") 
        
        with col_exp2: 
            # Export Excel 
            output = io.BytesIO() 
            with pd.ExcelWriter(output, engine='openpyxl') as writer: 
                df_classement_individuel.to_excel(writer, sheet_name='Classement Individuel') 
            excel_data = output.getvalue() 
            fname = f"classement_individuel_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx" 
            st.download_button("📊 Excel", excel_data, fname,  
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, key="exporter_classement_individuel_xlsx") 
        
        with col_exp3: 
            # Export PDF 
            pdf_data = generer_pdf_classement_individuel() 
            fname = f"classement_individuel_{st.session_state.nom_tournoi}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf" 
            st.download_button("📄 PDF", pdf_data, fname, "application/pdf", use_container_width=True, key="exporter_classement_individuel_pdf") 
        
        # Statistiques 
        st.divider() 
        st.subheader("📈 Statistiques") 
        
        col_stat1, col_stat2, col_stat3 = st.columns(3) 
        with col_stat1: 
            st.metric("Joueurs classés", len(df_classement_individuel))
        with col_stat2: 
            meilleur_score = df_classement_individuel["Score"].max() 
            st.metric("Meilleur score", f"{meilleur_score}")
        with col_stat3: 
            moyenne_diff = df_classement_individuel["Diff"].mean() 
            st.metric("Différence moyenne", f"{moyenne_diff:.1f}")
    
    else: 
        st.info("Aucun match joué pour le moment. Le classement individuel apparaîtra après les premiers matchs.")
                        
# ONGLET PARAMÈTRES 
if est_organisateur(): 
    with tabs[5]: 
        st.subheader("⚙️ Configuration Générale") 
        
        nouveau_nom = st.text_input("Nom du Tournoi", st.session_state.nom_tournoi, key="nom_tournoi_input") 
        if nouveau_nom != st.session_state.nom_tournoi: 
            st.session_state.nom_tournoi = nouveau_nom 
            st.rerun() 
        
        st.session_state.nb_terrains = st.number_input("Nombre de terrains", 1, 50, st.session_state.nb_terrains, key="nb_terrains_input") 
        
        # Mode du tournoi 
        st.divider() 
        st.subheader("🎮 Mode du Tournoi") 
        mode_tournoi = st.radio( 
            "Type de tournoi:", 
            ["Classique", "Individuel"], 
            index=0 if st.session_state.mode_tournoi == "Classique" else 1, 
            help="Classique: Équipes fixes, classement par équipe valide. Individuel: Équipes aléatoires à chaque round, seul le classement individuel a du sens.",
            key="mode_tournoi_radio"
        ) 
        if mode_tournoi != st.session_state.mode_tournoi: 
            st.session_state.mode_tournoi = mode_tournoi 
            if mode_tournoi == "Individuel": 
                st.warning("⚠️ Passage en mode Individuel: Les équipes seront regénérées aléatoirement à chaque nouveau round.") 
            st.rerun() 
        
        # Méthodes de classement 
        st.divider() 
        st.subheader("📊 Méthodes de classement") 
        
        col_algo1, col_algo2 = st.columns(2) 
        with col_algo1: 
            st.session_state.algo_classement = st.radio( 
                "Classement par équipe:", 
                ["Pondéré", "Standard"], 
                index=0 if st.session_state.algo_classement == "Pondéré" else 1,
                key="algo_classement_radio"
            ) 
        with col_algo2: 
            st.session_state.algo_classement_individuel = st.radio( 
                "Classement individuel:", 
                ["Pondéré", "Standard"], 
                index=0 if st.session_state.algo_classement_individuel == "Pondéré" else 1,
                key="algo_classement_individuel_radio"
            ) 
        
        st.divider() 
        st.subheader("🏷️ Catégories et Coefficients") 
        
        for cat, coef in list(st.session_state.categories_dict.items()): 
            if cat == "Joker": 
                continue 
            c1, c2, c3 = st.columns([2, 2, 1]) 
            c1.write(f"**{cat}**") 
            new_c = c2.number_input(f"Coeff", 0.5, 3.0, coef, 0.05, key=f"cfg_{cat}", label_visibility="collapsed") 
            st.session_state.categories_dict[cat] = new_c 
            if c3.button("Supprimer", key=f"del_{cat}"): 
                del st.session_state.categories_dict[cat] 
                st.rerun() 
        
        with st.expander("➕ Ajouter une catégorie"): 
            nc1, nc2 = st.columns(2) 
            n_name = nc1.text_input("Nom (ex: Espoir)", key="nouvelle_categorie_nom") 
            n_coef = nc2.number_input("Coeff", 0.5, 3.0, 1.0, 0.05, key="nouvelle_categorie_coeff") 
            if st.button("Enregistrer catégorie", key="enregistrer_categorie"): 
                if n_name and n_name != "Joker": 
                    st.session_state.categories_dict[n_name] = n_coef 
                    st.rerun() 
        
        st.divider() 
        st.subheader("🖼️ Personnalisation visuelle") 
        
        img_fond = st.file_uploader("Image de fond (JPG/PNG)", type=["jpg", "jpeg", "png"], key="image_fond_uploader") 
        if img_fond: 
            st.session_state.bg_image_data = img_fond 
            st.rerun() 
        
        if st.session_state.bg_image_data is not None: 
            if st.button("🗑️ Supprimer l'image de fond", key="supprimer_image_fond"): 
                st.session_state.bg_image_data = None 
                st.rerun() 
        
        st.divider() 
        st.subheader("⚙️ Import/Export Paramètres") 
        
        cp1, cp2 = st.columns(2) 
        with cp1: 
            params_json = exporter_parametres() 
            fname = f"parametres_{st.session_state.nom_tournoi}_{datetime.now().strftime('%Y%m%d_%H%M')}.json" 
            st.download_button("📤 Exporter paramètres", params_json, fname, "application/json", use_container_width=True, key="exporter_parametres") 
        
        with cp2: 
            uparam = st.file_uploader("📥 Importer paramètres", type=['json'], key="iparam") 
            if uparam and st.button("Charger les paramètres", use_container_width=True, key="charger_parametres"): 
                success, msg = importer_parametres(uparam) 
                if success: 
                    st.success(msg) 
                    st.rerun() 
                else: 
                    st.error(msg) 
        
        st.divider() 
        st.subheader("🔄 Réinitialisation") 
        
        # Bouton réinitialiser matchs 
        if not st.session_state.confirm_reset_matchs: 
            if st.button("🔄 Réinitialiser les Matchs & Classement", use_container_width=True, key="reinit_matchs_btn"): 
                st.session_state.confirm_reset_matchs = True 
                st.rerun() 
        else: 
            st.warning("⚠️ Êtes-vous sûr de vouloir réinitialiser tous les matchs et le classement? Cette action est irréversible!") 
            c1, c2 = st.columns(2) 
            with c1: 
                if st.button("✅ OUI, Réinitialiser", use_container_width=True, type="primary", key="confirmer_reinit_matchs"): 
                    reinitialiser_matchs() 
                    st.rerun() 
            with c2: 
                if st.button("❌ Annuler", use_container_width=True, key="annuler_reinit_matchs"): 
                    st.session_state.confirm_reset_matchs = False 
                    st.rerun() 
        
        st.divider() 
        
        # Bouton réinitialiser tournoi 
        if not st.session_state.confirm_reset_tournoi: 
            if st.button("⏱️ RÉINITIALISER TOUT LE TOURNOI", use_container_width=True, key="reinit_tout_btn"): 
                st.session_state.confirm_reset_tournoi = True 
                st.rerun() 
        else: 
            st.error("🚨 ATTENTION: Vous allez supprimer TOUTES les données du tournoi (joueurs, équipes, matchs)! Cette action est IRRÉVERSIBLE!") 
            c1, c2 = st.columns(2) 
            with c1: 
                if st.button("✅ OUI, Tout Supprimer", use_container_width=True, type="primary", key="confirmer_reinit_tout"): 
                    reinitialiser_tournoi() 
                    st.rerun() 
            with c2: 
                if st.button("❌ Annuler", use_container_width=True, key="annuler_reinit_tout"): 
                    st.session_state.confirm_reset_tournoi = False 
                    st.rerun()