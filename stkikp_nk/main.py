from flask import (
    Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for, jsonify
)
import os
from werkzeug.exceptions import abort
from joblib import load
import re
from stkikp_nk.auth import login_required
from stkikp_nk.db import get_db
from stkikp_nk.process import nlp, cbr

bp = Blueprint('main', __name__)

def delete_saved_input_threshold():
    if session.get('input'):
        session.pop('input')
    if session.get('threshold'):
        session.pop('threshold')

@bp.route('/input', methods=('GET', 'POST'))
@login_required
def input():

    input = session.get('input')
    if not input:
        input = ""

    threshold = session.get('threshold')
    if not threshold:
        threshold = 0.5

    if request.method == 'POST':

        # Get Form Data
        input = request.form.get('input')
        threshold = request.form.get('threshold')
        errors = []

        # Validation
        if not input:
            errors += ['Anda perlu memasukkan input.']
        if threshold == '0' or not threshold:
            errors += ['Anda perlu memasukkan nilai ambang.']    
        if re.search('[a-zA-Z]', input) is None:
            errors += ["Anamnesa harus memiliki huruf di dalamnya."]

        if errors: # Validation failed
            for error in errors:
                flash(error)
            return render_template('main/input.html', input=input, threshold=threshold)
        else: # Validation success
            session['input'] = input
            session['threshold'] = threshold
            return redirect(url_for("main.result"))

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
        session['icd_x'] = cbr_result
        session['symptoms_and_codes'] = symptoms_and_codes

        return render_template('main/result.html', input=input, preprocessed_string=preprocessed_string, corrected_string=corrected_string, symptoms_and_codes=symptoms_and_codes, cbr_result=cbr_result)
    
    else:

        return redirect(url_for('main.input'))

@bp.route('/instruction')
@login_required
def instruction():
    cbr_result = session.get('icd_x')
    if cbr_result:
        return render_template('main/instruction.html', cbr_result=cbr_result)
    else:
        return redirect(url_for('main.input'))

@bp.route('/case_manager')
@login_required
def case_manager():
    delete_saved_input_threshold()
    db = get_db()
    cases = db.execute("SELECT * FROM cases").fetchall()
    return render_template('main/case_manager.html', cases=cases)

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
        
        else: # Validation success
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
            
    if request.args.get('from_result') and request.method == 'GET': # If new_case accessed from result

        icd_x = session.get('icd_x')
        symptoms_and_codes = session.get('symptoms_and_codes')
        symptom_raw = session.get('input').split(";")
        symptom_normalized = [symptom[0] for symptom in symptoms_and_codes]
        symptom_code = []
        symptom_negativity = []
        for symptom in symptoms_and_codes:
            code = symptom[1][0]
            negativity = "1" if code[0] == "X" else "0"
            code = code[1:] if code[0] == "X" else code
            symptom_code.append(code)
            symptom_negativity.append(negativity)
        print(symptom_code)
        print(symptom_negativity)
        zipped_symptoms = zip(symptom_raw, symptom_normalized, symptom_code, symptom_negativity)
        return render_template('main/new_case.html', icd_x_list=icd_x_list, symptom_list=symptom_list, icd_x=icd_x, symptoms=zipped_symptoms)
    
    else: # If new_case accessed from case_manager

        delete_saved_input_threshold()
        return render_template('main/new_case.html', icd_x_list=icd_x_list, symptom_list=symptom_list)

@bp.route('/edit_case/<int:case_id>', methods=('GET', 'POST'))
@login_required
def edit_case(case_id):

    delete_saved_input_threshold()
    db = get_db()
    icd_x_list = db.execute('SELECT DISTINCT icd_code FROM cases ORDER BY icd_code ASC;').fetchall()
    symptom_list = db.execute('SELECT symptom, symptom_code FROM symptom_codes;').fetchall()
    case = db.execute("SELECT case_id, icd_code FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    symptoms = db.execute('SELECT * FROM symptoms WHERE case_id = ?', (case_id,)).fetchall()
    errors = []

    if request.method == 'POST':

        # Get Form Data
        case_id = case[0]
        icd_x = request.form.get('icd_x')
        symptom_raw = request.form.getlist('symptom_raw')[1:]
        symptom_normalized = request.form.getlist('symptom_normalized')[1:]
        symptom_code = request.form.getlist('symptom_code')[1:]
        symptom_negativity = request.form.getlist('symptom_negativity')[1:]
        zipped_symptoms = zip(symptom_raw, symptom_normalized, symptom_code, symptom_negativity)

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
            return render_template('main/edit_case.html', icd_x_list=icd_x_list, symptom_list=symptom_list, case_id=case_id, icd_x=icd_x, symptoms=zipped_symptoms)
        
        else: # Validation success
            raw_case = ";".join(map(str, symptom_raw))
            normalized_case = ";".join(map(str, symptom_normalized))
            try:
                # Update case
                db.execute(
                    "UPDATE cases SET raw_text = ?, normalized_text = ?, icd_code = ? WHERE case_id = ?;",
                    (raw_case, normalized_case, icd_x, case_id),
                )
                # Delete old symptoms
                db.execute(
                    "DELETE from symptoms WHERE case_id = ?;",
                    (case_id,),
                )
                # Insert new symptoms
                for raw_symptom, normalized_symptom, symptom_code, symptom_negativity in zipped_symptoms:
                    db.execute(
                        "INSERT INTO symptoms (case_id, raw_text, normalized_text, negativity, symptom_code) VALUES (?, ?, ?, ?, ?)",
                        (case_id, raw_symptom, normalized_symptom, symptom_negativity, symptom_code),
                    )
                db.commit()
            except Exception as e:
                flash('Galat terjadi ({}). Kasus tidak dapat diubah.'.format(e))
                return render_template('main/edit_case.html', icd_x_list=icd_x_list, symptom_list=symptom_list, case_id=case_id, icd_x=icd_x, symptoms=zipped_symptoms)
            else:
                flash('Kasus berhasil diubah.')
                return redirect(url_for('main.case_manager'))

    if case and symptoms:
        case_id = case[0]
        icd_x = case[1]
        symptom_raw = [symptom[2] for symptom in symptoms]
        symptom_normalized = [symptom[3] for symptom in symptoms]
        symptom_code = [symptom[5] for symptom in symptoms]
        symptom_negativity = [str(symptom[4]) for symptom in symptoms]
        zipped_symptoms = zip(symptom_raw, symptom_normalized, symptom_code, symptom_negativity) 
        return render_template('main/edit_case.html', icd_x_list=icd_x_list, symptom_list=symptom_list, case_id=case_id, icd_x=icd_x, symptoms=zipped_symptoms)
    else:
        flash('Kasus tidak ditemukan.')
        return redirect(url_for('main.case_manager'))

@bp.route('/delete_case/<int:case_id>', methods=('GET', 'POST'))
@login_required
def delete_case(case_id):

    db = get_db()
    query_result = db.execute('SELECT case_id FROM cases WHERE case_id = ?', (case_id,)).fetchone()

    # Validation
    query_result = query_result[0] if query_result else 0

    if case_id == query_result: # Validation success
        db.execute('DELETE FROM cases WHERE case_id = ?', (case_id,))
        db.execute('DELETE FROM symptoms WHERE case_id = ?', (case_id,))
        db.commit()
        if request.method == 'GET':
            flash("Kasus dengan ID {} telah dihapus.".format(case_id))
            return redirect(url_for('main.case_manager'))
        else:
            return "Kasus dengan ID {} telah dihapus.".format(case_id)
        
    else: # Validation failed
        flash("Kasus tidak ditemukan.")
        return redirect(url_for('main.case_manager'))