import pandas as pd
import numpy as np
import re
from collections import Counter
from joblib import dump, load
import os
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.metrics import accuracy_score, precision_score, recall_score, classification_report

def preprocess(input):
  #String -> String, mengubah tanda +,-,->,x di dalam input, mengembalikannya menjadi string.
  change_dict = {r';':r' ; ',
                 r'([0-9]+),([0-9]+)':r'\1.\2',
                 r',':r' , ',
                 r'->':r' ke ',
                 r'\+-':r' kurang lebih ',
                 r'/':r' atau ',
                 r'([A-Za-z0-9]+)-([A-Za-z0-9]+)':r"\1 sampai \2",
                 r'([0-9]+)([a-zA-Z]+)':r'\1 \2',
                 r'([a-zA-Z]+)2':r'\1 \1',
                 r'\+([0-9]+)':r' plus \1',
                 r'-([0-9]+)':r' minus \1',
                 r'\+ ([0-9]+)':r' plus \1',
                 r'- ([0-9]+)':r' minus \1',
                 r'\(\+\)':r'',
                 r'\( \+ \)':r'',
                 r'\+':r'',
                 r'\(-\)':r' nihil ',
                 r'\( - \)':r' nihil ',
                 r'-':r' nihil ',
                 r'\(':r'',
                 r'\)':r'',
                 r'\s+':r' '}

  def regex_change(regex,input,change):
    input = re.sub(regex, change, input)
    return input

  for regex in change_dict.keys():
    input = regex_change(regex, input, change_dict[regex])
  input = input.strip().lower()

  return input

def correct_input(input, db):
  #String -> String, mengkoreksi string, mengembalikannya menjadi string.
  #Correcting word (using normalized symptom)
  #http://norvig.com/spell-correct.html

  def words(text): return re.findall(r'\w+', text.lower())

  normalized_case_str = db.execute("SELECT normalized_text FROM cases").fetchall()
  normalized_case_str = " ".join([normalized_case[0] for normalized_case in normalized_case_str])
  normalized_case_str = normalized_case_str.replace(";", " ")
  WORDS = Counter(words(normalized_case_str))

  def known(words):
    "The subset of `words` that appear in the dictionary of WORDS."
    return set(w for w in words if w in WORDS)

  def candidates(word):
    "Generate possible spelling corrections for word."
    return (known([word]) or known(edits1(word)) or known(edits2(word)) or [word])

  def P(word, N=sum(WORDS.values())):
    "Probability of `word`."
    return WORDS[word] / N

  def correction(word):
    "Most probable spelling correction for word."
    return max(candidates(word), key=P)

  def edits1(word):
    "All edits that are one edit away from `word`."
    letters    = 'abcdefghijklmnopqrstuvwxyz'
    splits     = [(word[:i], word[i:])    for i in range(len(word) + 1)]
    deletes    = [L + R[1:]               for L, R in splits if R]
    transposes = [L + R[1] + R[0] + R[2:] for L, R in splits if len(R)>1]
    replaces   = [L + c + R[1:]           for L, R in splits if R for c in letters]
    inserts    = [L + c + R               for L, R in splits for c in letters]
    return set(deletes + transposes + replaces + inserts)

  def edits2(word):
    "All edits that are two edits away from `word`."
    return (e2 for e1 in edits1(word) for e2 in edits1(e1))

  input = input.split(";")

  for index in range(len(input)):
    sentence = input[index]
    splitted = sentence.split()
    for word in splitted:
        sentence = sentence.replace(word, correction(word))
    input[index] = sentence

  return ";".join(input)

def read_labelled_symptom_csv(db):
  query = """SELECT 
            normalized_text,
            CASE
              WHEN negativity IS '1' AND symptom_code IS NOT 'T' AND symptom_code IS NOT 'O'
                THEN 'X' || symptom_code
              ELSE symptom_code
            END AS symptom_code
            FROM symptoms;"""
  return pd.read_sql_query(query, db)

def nlp_model_init(app, db):
  #Vectorizer
  labelled_symptom_df = read_labelled_symptom_csv(db)
  SymptomVectorizer = CountVectorizer(ngram_range=(1,3))
  SymptomVectorizer.fit(labelled_symptom_df['normalized_text'])
  dump(SymptomVectorizer, os.path.join(app.instance_path, 'symptom_vectorizer.joblib')) 
  #Classifier
  X_train = SymptomVectorizer.transform(labelled_symptom_df['normalized_text'])
  y_train = labelled_symptom_df['symptom_code']
  SymptomClassifier = LogisticRegression()
  SymptomClassifier.fit(X_train, y_train)
  dump(SymptomClassifier, os.path.join(app.instance_path, 'symptom_classifier.joblib'))
  return SymptomVectorizer, SymptomClassifier

def get_nlp_model(app, db):
  if not os.path.exists(os.path.join(app.instance_path, 'symptom_vectorizer.joblib')) or not os.path.exists(os.path.join(app.instance_path, 'symptom_classifier.joblib')):
    SymptomVectorizer, SymptomClassifier = nlp_model_init(app, db)
    message = 'New Model Created.'
  else:
    SymptomVectorizer = load(os.path.join(app.instance_path, 'symptom_vectorizer.joblib')) 
    SymptomClassifier = load(os.path.join(app.instance_path, 'symptom_classifier.joblib'))
    message = 'Old Model Loaded.'
  return SymptomVectorizer, SymptomClassifier, message

def predict_symptom(symptom, classifier, threshold, label_under_treshold, label_pass_threshold):
  proba = (classifier.predict_proba(symptom))[0]
  classes = classifier.classes_
  df_result = pd.DataFrame({'label':classes, 'prob':proba}).sort_values(by=['prob'], ascending=False).iloc[0]
  result = [df_result['label'], df_result['prob']]
  result += [label_under_treshold] if df_result['prob'] < threshold else [label_pass_threshold]
  return result

def predict_case(input, vectorizer, classifier, threshold, label_under_treshold, label_pass_threshold):
  case_list = input.split(";")
  case_list = [symptom.strip() for symptom in case_list]
  #result = {symptom : predict_symptom(vectorizer.transform([symptom]), classifier, threshold, label_under_treshold) for symptom in case_list}
  case_list = [[symptom, predict_symptom(vectorizer.transform([symptom]), classifier, threshold, label_under_treshold, label_pass_threshold)] for symptom in case_list]
  return case_list