import boto3
import csv
import os
import requests
import zipfile


WORKSPACE = '/tmp'
ZIP_FILE_NAME = 'ken_all.zip'
CSV_FILE_NAME = 'KEN_ALL.CSV'
ZIP_CODE_URL = 'https://www.post.japanpost.jp/zipcode/dl/kogaki/zip/ken_all.zip'

table_name = 'ZipCode'
zip_code_table = boto3.resource('dynamodb').Table(table_name)


def main(*args, **kwargs):
    try:
        # ファイルダウンロード
        print('ファイルダウンロード開始')
        res = requests.get(ZIP_CODE_URL, stream=True)

        # ファイル保存
        print('ファイル保存開始')
        with open(f'{WORKSPACE}/{ZIP_FILE_NAME}', 'wb') as f:
            for chunk in res.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
                    f.flush()

        # ファイル解凍
        print('ファイル解凍開始')
        with zipfile.ZipFile(f'{WORKSPACE}/{ZIP_FILE_NAME}', 'r') as zip_file:
            zip_file.extractall(WORKSPACE)

        # データ整形
        print('データ整形開始')
        zip_codes = []
        with open(f'{WORKSPACE}/{CSV_FILE_NAME}', "r", encoding="ms932", errors="", newline="") as csv_file:
            reader = csv.reader(csv_file)
            for row in reader:
                zip_codes.append(dict(
                    zipCode=row[2],
                    prefecture=row[6],
                    prefectureKana=row[3],
                    city=row[7],
                    cityKana=row[4],
                    street=row[8],
                    streetKana=row[5]
                ))

        # 取り込み
        print('取り込み開始')
        with zip_code_table.batch_writer(overwrite_by_pkeys=['zipCode']) as batch:
            for zip_code in zip_codes:
                batch.put_item(Item=zip_code)
    finally:
        write_capacity_scaledown()
        os.remove(f'{WORKSPACE}/{ZIP_FILE_NAME}')
        os.remove(f'{WORKSPACE}/{CSV_FILE_NAME}')


def write_capacity_scaleup(*args, **kwargs):
    zip_code_table.update(
        ProvisionedThroughput={
            'ReadCapacityUnits': 5,
            'WriteCapacityUnits': 1000
        }
    )


def write_capacity_scaledown(*args, **kwargs):
    zip_code_table.update(
        ProvisionedThroughput={
            'ReadCapacityUnits': 5,
            'WriteCapacityUnits': 1
        }
    )
