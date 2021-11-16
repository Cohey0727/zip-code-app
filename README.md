# SAMをつかったサーバーレスな郵便番号APIを紹介！
## はじめに
郵便番号から住所を検索するAPIってなんで無料で存在しないんだってよく思います。(ほんとにないかはよく調べてないので知りませんが。)
なので簡単にデプロイして公開して自動更新までしてくれるアプリケーションをSAMをつかって作成したので紹介します。
またSAMのチュートリアルに丁度いいくらいの量だと思いますので、ぜひ[実装解説](#実装解説)も見てみてください。
この記事で紹介しているソースコードはこちらです。
https://github.com/Cohey0727/zip-code-app

### 構成について
日本郵便株式会社は郵便番号と住所を紐づけたCSVファイルを公開しています。https://www.post.japanpost.jp/zipcode/download.html
ですがCSVファイルのままだとWeb画面などで利用するのは難しいです。
そこでLambdaでファイルをダウンロードして検索可能な状態でDynamoDBに格納する関数とそれをAPIとして公開する関数、定期的にそれらを更新するイベントをSAMで作成しています。
![Untitled Diagram.png](https://qiita-image-store.s3.ap-northeast-1.amazonaws.com/0/235240/51711bce-71d3-3745-197b-e8c754c5da03.png)


### SAMとは
SAMとはAWSのマネージドなサービスを組み合わせて、サーバーレスアプリケーションを構築できるフレームワークです。
cliが提供されており、この記事の実装やデプロイの際にインストールが必要になります。
[AWS SAM CLI のインストール
](https://docs.aws.amazon.com/ja_jp/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html)

### 環境

| 項目    | バージョン |
| ------- | ---------- |
| SAM CLI | 1.6.2      |
| Python  | 3.8        |


### とにかく動作させたい方へ
実装等はどうでもいいので、とにかく動作させたいという方は、`git clone https://github.com/Cohey0727/zip-code-app.git`をして[デプロイ&動作確認](#デプロイ動作確認)の章から読んでください。
また`master`ブランチでは定期的に郵便番号を更新するプログラムを含みます。不要な場合はブランチを`none_schedule`に切り替えてからデプロイ&動作確認を実施してください。


## 実装解説
ここでは具体的なプログラムや構成の解説をしていきます。
逐次[デプロイ&動作確認](#デプロイ&動作確認)しながらやるとより理解が深まると思います。

### 初期化
`sam init`コマンドで初期化します。
以下のパラメータで初期化しています。

| 項目                  | 選択                      | 値           |
| --------------------- | ------------------------- | ------------ |
| template source       | AWS Quick Start Templates | 1            |
| runtime               | python3.8                 | 2            |
| Project name          | -                         | zip-code-app |
| application templates | Hello World Example       | 1            |


<details>
<summary>クリックでコマンド結果を展開</summary>
<div>

```shell
$ sam init
Which template source would you like to use?
        1 - AWS Quick Start Templates
        2 - Custom Template Location
Choice: 1

Which runtime would you like to use?
        1 - nodejs12.x
        2 - python3.8
        3 - ruby2.7
        4 - go1.x
        5 - java11
        6 - dotnetcore3.1
        7 - nodejs10.x
        8 - python3.7
        9 - python3.6
        10 - python2.7
        11 - ruby2.5
        12 - java8.al2
        13 - java8
        14 - dotnetcore2.1
Runtime: 2

Project name [sam-app]: zip-code-app

AWS quick start application templates:
        1 - Hello World Example
        2 - EventBridge Hello World
        3 - EventBridge App from scratch (100+ Event Schemas)
        4 - Step Functions Sample App (Stock Trader)
        5 - Elastic File System Sample App
Template selection: 1

-----------------------
Generating application:
-----------------------
Name: zip-code-app
Runtime: python3.8
Dependency Manager: pip
Application Template: hello-world
Output Directory: .

Next steps can be found in the README file at ./zip-code-app/README.md

```

</div>
</details>

今回は`src`フォルダを作成しそこにプログラムを書くことにします。
また`src/requirements.txt`に必要なライブラリを追記します。

```shell
$ mkdir src
$ touch src/__init__.py
$ touch src/requirements.txt
$ echo "requests" >> src/requirements.txt
```

また不要なファイルと不要なリソースを削除します。

```shell
$ rm -rf hello_world
```

AWSで利用するリソースは`template.yaml`に記述していきます。
不要な部分を削除しておきます。

```diff
--- a/template.yaml
+++ b/template.yaml

 Resources:
-  HelloWorldFunction:
-    Type: AWS::Serverless::Function ## More info about Function Resource: https://github.com/awslabs/serverless-application-model/blob/master/versions/2016-10-31.md#awsserverlessfunction
-    Properties:
-      CodeUri: hello_world/
-      Handler: app.lambda_handler
-      Runtime: python3.8
-      Events:
-        HelloWorld:
-          Type: Api ## More info about API Event Source: https://github.com/awslabs/serverless-application-model/blob/master/versions/2016-10-31.md#api
-          Properties:
-            Path: /hello
-            Method: get
 
```


最終的なフォルダ構成は以下のようになります。

```
.
├── README.md
├── __init__.py
├── events
│   └── event.json
├── src
│   ├── __init__.py
│   └── requirements.txt
├── template.yaml
└── tests
    ├── __init__.py
    ├── integration
    │   ├── __init__.py
    │   └── test_api_gateway.py
    ├── requirements.txt
    └── unit
        ├── __init__.py
        └── test_handler.py
```

### DBの設計・実装
AWSのDynamoDBを利用して作成します。
**郵便番号 -> 住所**で検索したいので郵便番号に該当するカラムに`PrimaryIndex`を指定します。
今回は郵便番号のカラムを`zipCode`としました。
また、WriteCapacityUnitsは初回のデータ取り込み時を除いて全く必要ないので最小の1ユニットを指定します。

以下のコードを`template.yaml`の`Resources`のブロックに追記します。

```template.yaml
  ZipCodeTable:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: ZipCode
      AttributeDefinitions:
        - AttributeName: zipCode
          AttributeType: S
      ProvisionedThroughput:
        ReadCapacityUnits: 5
        WriteCapacityUnits: 1
      KeySchema:
        - AttributeName: zipCode
          KeyType: HASH
```

DynamoDBはスキーマレスなので、インデックスに指定しないカラムは記述しません。なのでこれでDBに関する記述は終了です。[デプロイ](#デプロイ)するとコンソール画面からテーブルが作成されていることが確認できます。

### 郵便番号の取り込みを実装
郵便番号の取り込み用のソースコードのは`import.py`ファイルに記述していきます。

```shell
$ touch src/import.py
```
#### 定数と初期化
先に作業用ディレクトリ、ダウンロードファイル名、解凍ファイル名、ダウンロードURLを定数にしておきます。
また、boto3よりテーブルリソースを取得しておきます。

```python
import boto3
import csv
import os
import requests
import zipfile

WORKSPACE = f'/tmp'
ZIP_FILE_NAME = 'ken_all.zip'
CSV_FILE_NAME = 'KEN_ALL.CSV'
ZIP_CODE_URL = 'https://www.post.japanpost.jp/zipcode/dl/kogaki/zip/ken_all.zip'

table_name = 'ZipCode'
zip_code_table = boto3.resource('dynamodb').Table(table_name)
```
  
#### ファイルのダウンロードと解凍
ファイルをダウンロード、解凍します。

```python
## ファイルダウンロード
res = requests.get(ZIP_CODE_URL, stream=True)

## ファイル保存
with open(f'{WORKSPACE}/{ZIP_FILE_NAME}', 'wb') as f:
    for chunk in res.iter_content(chunk_size=1024):
        if chunk:
            f.write(chunk)
            f.flush()

## ファイル解凍
with zipfile.ZipFile(f'{WORKSPACE}/{ZIP_FILE_NAME}', 'r') as zip_file:
    zip_file.extractall(WORKSPACE)

```

#### データの整形と取り込み
  
日本郵政からダウンロードしたCSVファイルは以下のような構成になっています。
[参考](https://www.post.japanpost.jp/zipcode/dl/readme.html)

| No  | 内容                   |
| --- | ---------------------- |
| 1   | 全国地方公共団体コード |
| 2   | 旧郵便番号(5桁)        |
| 3   | 郵便番号(7桁)          |
| 4   | 都道府県名カナ         |
| 5   | 市区町村名カナ         |
| 6   | 町域名カナ             |
| 7   | 都道府県名             |
| 8   | 市区町村名             |
| 9   | 町域名                 |

3カラム目の`郵便番号(7桁)`が`PrimaryIndex`である`zipCode`を当てはまります。
それ以外にはそれっぽい英語のカラムを適用します。


```python
## 整形
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

## 取り込み
with zip_code_table.batch_writer(overwrite_by_pkeys=['zipCode']) as batch:
    for zip_code in zip_codes:
        batch.put_item(Item=zip_code)
```

#### 定期取り込みの登録
初回取り込みのみで問題ないという場合は、この章は呼び飛ばしてください。

このアプリケーションの場合、書き込みキャパシティーがデータ取り込み時とそうでないときで大きな差があるためそれを管理する必要があります。
処理の流れとしては**キャパシティーを拡張→10分待つ→実行→キャパシティーを元に戻す**と処理が少し複雑になります。(キャパシティーモードをオンデマンドにすれば解決しますが、無料枠でどうにかしたかったのでこの方法を採用しています)

まず、書き込みキャパシティを拡張する関数とそれを元に戻す関数を`import.py`に追記します。

```python
## import.py
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

```

続いて関数が定期実行されるように`template.yaml`に追記しきます。`write_capacity_scaledown`は取り込み処理の最後に追記します。
今回は**毎年、日本時間の4月10日のAM00:00分にスケールアップ→4月1日のAM00:10に取り込み処理開始&スケールダウン**するようにしています。

以下のコードを`template.yaml`の`Resources`のブロックに追記します。

```yaml
  ImportZipCodeFunc:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: src/
      Handler: import.main
      Runtime: python3.8
      Policies:
        - DynamoDBCrudPolicy:
            TableName: ZipCode
        - DynamoDBReconfigurePolicy:
            TableName: ZipCode
      Timeout: 600
      MemorySize: 512
      Events:
        ScheduleImport:
          Type: Schedule
          Properties:
            Schedule: cron(10 15 31 3 ? *)
  TableScaleUpFunc:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: src/
      Handler: import.write_capacity_scaleup
      Runtime: python3.8
      Policies:
        - DynamoDBReconfigurePolicy:
            TableName: ZipCode
      Events:
        ScheduleImport:
          Type: Schedule
          Properties:
            Schedule: cron(0 15 31 3 ? *)

```
#### 完成形
以下がデータ取り込みの最終的なソースコードとなります。

```python
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
        ## ファイルダウンロード
        print('ファイルダウンロード開始')
        res = requests.get(ZIP_CODE_URL, stream=True)

        ## ファイル保存
        print('ファイル保存開始')
        with open(f'{WORKSPACE}/{ZIP_FILE_NAME}', 'wb') as f:
            for chunk in res.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
                    f.flush()

        ## ファイル解凍
        print('ファイル解凍開始')
        with zipfile.ZipFile(f'{WORKSPACE}/{ZIP_FILE_NAME}', 'r') as zip_file:
            zip_file.extractall(WORKSPACE)

        ## データ整形
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

        ## 取り込み
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

```

### 検索用APIの実装
#### 検索用プログラム
検索用のソースコードは`search.py`ファイルに記述していきます。

```shell
$ touch src/search.py
```

今回は`https://xxx.amazonaws.com/zipcode/123-4567`のようにパスパラメータとして郵便番号を受け取ることにします。

```python
import boto3
import json

table_name = 'ZipCode'
zip_code_table = boto3.resource('dynamodb').Table(table_name)


def main(event, context):
    zip_code_str = event['pathParameters'].get('zipCode').replace('-', '')
    params = {'zipCode': zip_code_str}
    zip_code = zip_code_table.get_item(Key=params).get('Item')
    return {'statusCode': 200, 'body': json.dumps(zip_code)} if zip_code else {'statusCode': 404}

```

パスパラメータはLambdaをハンドルしている関数の第一引数から`pathParameters`キーで取得できます。
またパスパラメータ内でのキーは`template.yaml`で宣言することができ、今回は`zipCode`としています。

`template.yaml`の`Resource`ブロックに以下を追記します。

```yaml
  ZipCodeSearchApi:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: src/
      Handler: search.main
      Runtime: python3.8
      Policies:
        - DynamoDBReadPolicy:
            TableName: ZipCode
      Events:
        ListSearchUser:
          Type: Api
          Properties:
            Path: /zipcode/{zipCode}
            Method: get
```

#### デプロイ後にAPIのURLを表示

`template.yaml`の`Outputs`のブロックには、デプロイが完了したあとにAPIのURLを出力することができます。

```yaml
Outputs:
  ZipCodeSearchApi:
    Description: "API Gateway endpoint URL for Search Address from Zip Code"
    Value: !Sub "https://${ServerlessRestApi}.execute-api.${AWS::Region}.amazonaws.com/Prod/zipcode/100-0000"
```

## デプロイ&動作確認
### デプロイ
以下のコマンドでアプリケーションをデプロイします。
スタック名やリージョンは、必要に応じて変更してください。

```shell
$ sam build
$ sam deploy --guided
        Stack Name [sam-app]: zip-code-app
        AWS Region [us-east-1]: ap-northeast-1
        #Shows you resources changes to be deployed and require a 'Y' to initiate deploy
        Confirm changes before deploy [y/N]: y
        #SAM needs permission to be able to create roles to connect to the resources in your template
        Allow SAM CLI IAM role creation [Y/n]: Y
        HelloWorldFunction may not have authorization defined, Is this okay? [y/N]: y
        Save arguments to configuration file [Y/n]: Y
        SAM configuration file [samconfig.toml]:
        SAM configuration environment [default]:
```

デプロイ後に出力されるURLがAPIのURLです。動作確認で利用するのでメモしておきます。
なおこちらAWSコンソールからいつでも確認できます。API Gateway > zip-code-app > ステージ > Prod

### 初回取り込み
上記のデプロイのみだと定期実行の日付までデータが存在しないので住所検索を利用することができません。
そのため初回のデータ取り込みが必要になります。

実行する前に書き込みキャパシティーユニットを拡張する必要があります。
私の実行したときは、500ユニットほどで頭打ちになったので1000ユニットあれば十分です。
AWSコンソールの**DynamoDB > テーブル > ZipCode > キャパシティ > 書き込みキャパシティーユニット**から変更できます。

![Group 1.png](https://qiita-image-store.s3.ap-northeast-1.amazonaws.com/0/235240/4afa2b6f-56c0-6ac0-a7de-7245c1cf67ae.png)

変更の反映には数分かかります。テーブルの更新が完了するまで待ってLambdaのダッシュボード画面から取り込み関数を実行します。
**Lambda > 関数 > zip-code-app-ImportZipCodeFunc-xxxx > 設定**から実行できます。
テストイベントを作成する必要がありますが、中身は参照しないのでサンプルをそのまま利用して問題ありません。

![Group 2.png](https://qiita-image-store.s3.ap-northeast-1.amazonaws.com/0/235240/623a8ddf-9098-6cfd-106d-81b3c267e0ed.png)

郵便番号は全部で約12万件あるので数分かかります。
完了したら、データが作成されていることと書き込みキャパシティーユニットが1に戻っていることを確認します。
![image.png](https://qiita-image-store.s3.ap-northeast-1.amazonaws.com/0/235240/344c7723-137a-4722-a1cc-526c337c4627.png)

### 動作確認
デプロイ後に出力されたURLをブラウザ等に貼り付けて動作を確認します。
Unicodeエスケープされているのでわかりにくいですが、レスポンスに住所情報が乗っています。(開発者ツールのNetwork > 対象のリクエスト > PreviewでUnicodeエスケープをデコードしてくれます。)
![image.png](https://qiita-image-store.s3.ap-northeast-1.amazonaws.com/0/235240/c2e0129d-be56-59e7-ca1c-14ae8cb216a5.png)


## さいごに
住所検索を利用・実装する際の選択肢のひとつになればと思います。
あとSAMやCloudFormationなど**Infrastructure as Code**フレームワークはこうしたアプリケーションの公開も簡単でとてもいいですね。
