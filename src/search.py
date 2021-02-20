import boto3
import json

table_name = 'ZipCode'
zip_code_table = boto3.resource('dynamodb').Table(table_name)


def main(event, context):
    zip_code_str = event['pathParameters'].get('zipCode').replace('-', '')
    params = {'zipCode': zip_code_str}
    zip_code = zip_code_table.get_item(Key=params).get('Item')
    return {'statusCode': 200, 'body': json.dumps(zip_code)} if zip_code else {'statusCode': 404}
