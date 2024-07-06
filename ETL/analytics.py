from airflow import DAG #to recognize this py is DAG file 
from datetime import timedelta, datetime
import json
import requests
from airflow.operators.python import PythonOperator
from airflow.operators.bash_operator import BashOperator
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
from airflow.providers.amazon.aws.transfers.s3_to_redshift import S3ToRedshiftOperator


# Load JSON config file
with open('/home/ubuntu/airflow/config_api.json', 'r') as config_file: #r means read, open the config file, remember to import json
    api_host_key = json.load(config_file)

now = datetime.now()
dt_now_string = now.strftime("%d%m%Y%H%M%S")

# Define the S3 bucket
s3_bucket = 'cleaned-data-zone-csv-bucket'

def extract_zillow_data(**kwargs): #kwargs means keyword args, can refer to the airflow documentation
    url = kwargs['url']
    headers = kwargs['headers']
    querystring = kwargs['querystring']
    dt_string = kwargs['date_string']
    # return headers
    response = requests.get(url, headers=headers, params=querystring) #same as rapid api
    response_data = response.json()
    

    # Specify the output file path
    output_file_path = f"/home/ubuntu/response_data_{dt_string}.json" #st_string filename in date format
    file_str = f'response_data_{dt_string}.csv' #this is for lambda later

    # Write the JSON response to a file
    with open(output_file_path, "w") as output_file: #write data to output_file
        json.dump(response_data, output_file, indent=4)  # indent for pretty formatting #is going to save inside Ubuntu EC2
    output_list = [output_file_path, file_str] #this list is used for later to access it, can access later by indexing 0, 1
    return output_list   

default_args = {
    'owner': 'airflow',
    'depends_on_past': False, #don't want the past
    'start_date': datetime(2023, 8, 1), #get data since when
    'email': ['myemail@domain.com'], #any email
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(seconds=15) #wait 15 seconds before 2nd retry
}


with DAG('zillow_analytics_dag', #dag id we give
        default_args=default_args,
        schedule_interval = '@daily', #run every 12 mignight
        catchup=False) as dag:

        extract_zillow_data_var = PythonOperator( #import PythonOperator #import json as we don't want to expose the api key
        task_id= 'tsk_extract_zillow_data_var', #any name
        python_callable=extract_zillow_data, #python callable can get from documentation,under airflow.operators.python, extract_zillow_data is a function name we give
        op_kwargs={'url': 'https://zillow56.p.rapidapi.com/search', 'querystring': {"location":"houston, tx"}, 'headers': api_host_key, 'date_string':dt_now_string} 
        #the parameter with used refer to the response paramater required by the API, add in additional date_string because want to use it to rename the filename according to date
        #op_kwargs is a dictionary of keyword arguments that will get unpacked in your function, refer to Airflow documentation
        #all the values in op_kwargs which are url, headers, querystring and date_string will pass to the above extract_zillow_data function
        )

        load_to_s3 = BashOperator(
            task_id = 'tsk_load_to_s3', #task id any name
            bash_command = 'aws s3 mv {{ ti.xcom_pull("tsk_extract_zillow_data_var")[0]}} s3://endtoendbucket/', #need to install aws dependency, mv means move, so here use aws command to move data from output_file_path to S3
            #ti means task in, allow to connect whatever previous task to get something from, xcom means cross communication, ti.xcom_pull can pull data from previous task, "tsk_extract_zillow_data_var" is the task id to pull from which is output_list, [0] means extract first thing "output_file_path"
        )

        is_file_in_s3_available = S3KeySensor(
        task_id='tsk_is_file_in_s3_available',
        bucket_key='{{ti.xcom_pull("tsk_extract_zillow_data_var")[1]}}', #bucket key is filename, [1] refer to index 1 of output list
        bucket_name=s3_bucket, #the bucket we are going to sense it
        aws_conn_id='aws_s3_conn',  #any name #need to create a connection in Airflow UI
        wildcard_match=False,  # Set this to True if you want to use wildcards in the prefix
        timeout=60,  # Optional: Timeout for the sensor (in seconds)
        poke_interval=5,  # Optional: Time interval between S3 checks (in seconds)
        )
        
        transfer_s3_to_redshift = S3ToRedshiftOperator(
        task_id="tsk_transfer_s3_to_redshift",
        aws_conn_id='aws_s3_conn',
        redshift_conn_id='conn_id_redshift',
        s3_bucket=s3_bucket,
        s3_key='{{ti.xcom_pull("tsk_extract_zillow_data_var")[1]}}',
        schema="PUBLIC",
        table="zillowdata",
        copy_options=["csv IGNOREHEADER 1"], #ignore header in row 1 of csv file
    )




        extract_zillow_data_var >> load_to_s3 >> is_file_in_s3_available >> transfer_s3_to_redshift