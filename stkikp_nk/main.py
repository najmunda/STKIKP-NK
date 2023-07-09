from flask import (
    Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for, jsonify
)
import os
from werkzeug.exceptions import abort
from joblib import load
import re
from NLPCBR.auth import login_required
from NLPCBR.db import get_db
from NLPCBR.process import nlp, cbr

bp = Blueprint('main', __name__)

@bp.route('/input', methods=('GET', 'POST'))
@login_required
def input():

    input = session.get('input')
    threshold = session.get('threshold')
    if not input:
        input = ""
    if not threshold:
        threshold = 0.5
        
    if request.method == 'POST':
        input = request.form['input']
        threshold = request.form['threshold']
        errors = []

        #validasi input
        if re.search('[a-zA-Z]', input) is None:
            errors += ["Anamnesa harus memiliki huruf di dalamnya."]

        if not len(errors):
            session['input'] = input
            session['threshold'] = threshold
            return redirect(url_for("main.result"))

        flash('\n'.join(errors))

    flash('test')
    return render_template('main/input.html', input=input, threshold=threshold)

@bp.route('/result')
@login_required
def result():
    input = session.get('input')
    if input:
        threshold = float(session.get('threshold'))
        db = get_db()

        #----NLP----
        preprocessed_string = nlp.preprocess(input)
        corrected_string = nlp.correct_input(preprocessed_string, db)
        SymptomVectorizer, SymptomClassifier, message = nlp.get_nlp_model(current_app, db)
        flash(message)
        symptoms_and_codes = nlp.predict_case(corrected_string, SymptomVectorizer, SymptomClassifier, float(threshold), 'Under Threshold', 'Passing Threshold')
        
        #----CBR----
        symptom_codes = [item[1][0] for item in symptoms_and_codes]
        symptom_code_vector = cbr.codes_to_vector(symptom_codes, db)
        saved_symptom_code_vector = cbr.db_to_vector(db)
        cbr_result = cbr.get_nearest_label(symptom_code_vector, saved_symptom_code_vector, threshold)
        session['cbr_result'] = cbr_result

        return render_template('main/result.html', input=input, preprocessed_string=preprocessed_string, corrected_string=corrected_string, symptoms_and_codes=symptoms_and_codes, cbr_result=cbr_result)
    
    else:
        return redirect(url_for('main.input'))

@bp.route('/instruction')
@login_required
def instruction():
    cbr_result = session.get('cbr_result')
    if cbr_result:
        return render_template('main/instruction.html', cbr_result=cbr_result)
    else:
        return redirect(url_for('main.input'))

@bp.route('/case_manager')
@login_required
def case_manager():
    db = get_db()
    cases = db.execute("SELECT * FROM cases").fetchall()
    return render_template('main/case_manager.html', cases=cases)

def symptom_form_to_list(symptom_raw, symptom_normalized, symptom_code, symptom_negativity):
    pass

@bp.route('/new_case', methods=('GET', 'POST'))
@login_required
def new_case():

    db = get_db()
    icd_x_list = db.execute('SELECT DISTINCT icd_code FROM cases ORDER BY icd_code ASC;').fetchall()
    symptom_list = db.execute('SELECT symptom, symptom_code FROM symptom_codes;').fetchall()
    errors = []

    if request.method == 'POST':

        # Get Form Data
        icd_x = request.form.get('icd_x')
        symptom_raw = request.form.getlist('symptom_raw')[1:]
        symptom_normalized = request.form.getlist('symptom_normalized')[1:]
        symptom_code = request.form.getlist('symptom_code')[1:]
        symptom_negativity = request.form.getlist('symptom_negativity')[1:]
        zipped_symptoms = zip(symptom_raw, symptom_normalized, symptom_code, symptom_negativity)
        print(icd_x)
        print(symptom_raw)
        print(symptom_normalized)
        print(symptom_code)
        print(symptom_negativity)
                
        # Validation
        if not icd_x:
            errors += ['Anda perlu memilih opsi kode ICD X.']
        if not (symptom_raw and symptom_normalized and symptom_code and symptom_negativity):
            errors += ['Anda perlu memasukkan sebuah gejala.']
        if '' in symptom_raw + symptom_normalized + symptom_code + symptom_negativity:
            errors += ['Anda perlu memasukkan seluruh detail gejala.']

        if errors: # Validation failed
            for error in errors:
                flash(error)
            return render_template('main/new_case.html', icd_x_list=icd_x_list, symptom_list=symptom_list, icd_x=icd_x, symptoms=zipped_symptoms)
        
        else: # Validation passed
            case_id = db.execute("SELECT seq + 1 FROM sqlite_sequence WHERE name = 'cases';").fetchone()[0]
            raw_case = ";".join(map(str, symptom_raw))
            normalized_case = ";".join(map(str, symptom_normalized))
            try:
                #Insert Case
                db.execute(
                        "INSERT INTO cases (case_id, raw_text, normalized_text, icd_code) VALUES (?, ?, ?, ?)",
                        (case_id, raw_case, normalized_case, icd_x),
                )
                #Insert Symptoms
                for raw_symptom, normalized_symptom, symptom_code, symptom_negativity in zipped_symptoms:
                    db.execute(
                            "INSERT INTO symptoms (case_id, raw_text, normalized_text, negativity, symptom_code) VALUES (?, ?, ?, ?, ?)",
                            (case_id, raw_symptom, normalized_symptom, symptom_negativity, symptom_code),
                    )
                db.commit()
            except Exception as e:
                flash('Galat terjadi ({}). Kasus tidak dapat ditambahkan.'.format(e))
                return render_template('main/new_case.html', icd_x_list=icd_x_list, symptom_list=symptom_list, icd_x=icd_x, symptoms=zipped_symptoms)
            else:
                flash('Kasus berhasil ditambahkan.')
                return redirect(url_for('main.case_manager'))                
            
    return render_template('main/new_case.html', icd_x_list=icd_x_list, symptom_list=symptom_list)

@bp.route('/edit_case/<int:case_id>', methods=('GET', 'POST'))
@login_required
def edit_case(case_id):
    db = get_db()
    icd_x_list = db.execute('SELECT DISTINCT icd_code FROM cases ORDER BY icd_code ASC;').fetchall()
    symptom_list = db.execute('SELECT symptom, symptom_code FROM symptom_codes;').fetchall()
    case = db.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    symptoms = db.execute('SELECT * FROM symptoms WHERE case_id = ?', (case_id,)).fetchall()
    if case and symptoms:
        return render_template('main/edit_case.html', icd_x_list=icd_x_list, symptom_list=symptom_list, case=case, symptoms=symptoms)
    else:
        return redirect(url_for('main.case_manager'))

@bp.route('/delete_case/<int:case_id>', methods=('GET', 'POST'))
@login_required
def delete_case(case_id):

    db = get_db()
    query_result = db.execute('SELECT case_id FROM cases WHERE case_id = ?', (case_id,)).fetchone()

    # Validation
    query_result = query_result[0] if query_result else 0

    if case_id == query_result: # Validation passed
        db.execute('DELETE FROM cases WHERE case_id = ?', (case_id,))
        db.execute('DELETE FROM symptoms WHERE case_id = ?', (case_id,))
        db.commit()
        if request.method == 'GET':
            flash("Kasus dengan ID {} telah dihapus.".format(case_id))
            return redirect(url_for('main.case_manager'))
        else:
            return "Kasus dengan ID {} telah dihapus.".format(case_id)
        
    else: # Validation failed
        flash("ID Kasus tidak ditemukan.")
        return redirect(url_for('main.case_manager'))