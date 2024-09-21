import yaml
from sklearn.feature_extraction.text import TfidfVectorizer


def read_file():
    with open("json/example3.json", 'r') as stream:
        schema = yaml.safe_load(stream)
    return schema

    print(schema)


if __name__ == '__main__':
    read_file()