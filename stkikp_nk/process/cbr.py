import pandas as pd
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

def load_symptom_code(db):
  query = """
          SELECT 
            symptom, 
            symptom_code 
          FROM 
            symptom_codes
          WHERE
            symptom_code NOT IN ("O","T")
          UNION ALL
          SELECT 
            IIF(symptom_code NOT IN ("O","T"), symptom || ' nihil', symptom) AS symptom,
            symptom_code_negate AS symptom_code 
          FROM 
            symptom_codes;
          """
  return pd.read_sql_query(query, db)

def codes_to_vector(input, db):
  symptom_code_df = load_symptom_code(db)
  symptom_code_list = [code for code in symptom_code_df['symptom_code']]
  #Remove unrelated symptom (signed by "O" & "T")
  input = list(filter(lambda a: a != "O", input))
  input = list(filter(lambda a: a != "T", input))
  #Change to feature. Signed by 1 and 0
  return [input.count(code) for code in symptom_code_list]

def load_saved_cases(db):
  query = """
          SELECT
            symptoms.case_id,
            GROUP_CONCAT(
              IIF(
                symptoms.negativity IS '1' AND 
                symptoms.symptom_code IS NOT 'T' AND 
                symptoms.symptom_code IS NOT 'O', 
                'X' || symptoms.symptom_code, 
                symptoms.symptom_code)
              ) AS symptoms_code,
            cases.icd_code
          FROM 
            cases
          INNER JOIN symptoms ON
            symptoms.case_id = cases.case_id
          GROUP BY
            cases.case_id;
          """
  return pd.read_sql_query(query, db)

def db_to_vector(db):
  symptom_code_df = load_symptom_code(db)
  data_from_db = load_saved_cases(db)
  for index in range(len(data_from_db)):
    if type(data_from_db['symptoms_code'][index]) == str:
      data_from_db['symptoms_code'][index] = data_from_db['symptoms_code'][index].split(",")
    if len(data_from_db['symptoms_code'][index]) != len(symptom_code_df['symptom_code']):
      data_from_db['symptoms_code'][index] = codes_to_vector(data_from_db['symptoms_code'][index], db)
  return data_from_db

def get_all_similarity(new_case, old_cases):
  new_case = np.array([new_case])
  old_cases_feature = np.array(list(old_cases['symptoms_code']))
  old_cases_target = list(old_cases['icd_code'])
  similarity = cosine_similarity(new_case, old_cases_feature)
  all_array = {"Feature": list(old_cases_feature),
              "Target": list(old_cases_target),
              "Similarity": list(similarity[0])}
  old_cases_with_similarity = pd.DataFrame(all_array)
  return old_cases_with_similarity.sort_values('Similarity', ascending=False)

def get_nearest_label(new_case, old_cases, threshold):
  old_cases_with_similarity = get_all_similarity(new_case, old_cases)
  return 'under_threshold' if old_cases_with_similarity['Similarity'].iloc[0] < threshold else old_cases_with_similarity['Target'].iloc[0] 