import os
import re
import csv
from typing import Type
import rdflib
from pathlib import Path
from rdflib.namespace import Namespace, RDF, RDFS, FOAF, OWL
from rdflib.term import URIRef


class Loader:

    def __init__(self):
        self.iri: str = None

        self.loader_location: Path = Path(__file__).parent
        self.data_location: Path = Path(os.path.join(self.loader_location.parent, 'data'))

        self.schema_file: Path = Path(os.path.join(self.data_location, 'schema.ttl'))
        self.soen321_file : Path = self.data_location / 'soen321.ttl'
        self.comp474_file : Path = self.data_location / 'comp474.ttl'

        self.open_data_file: Path = Path(os.path.join(self.data_location, 'CATALOG.csv'))
        self.open_data_with_extra: Path = Path(os.path.join(self.data_location, 'CU_SR_OPEN_DATA_CATALOG.csv'))
        self.open_data_with_desc: Path = Path(os.path.join(self.data_location, 'CU_SR_OPEN_DATA_CATALOG_DESC.csv'))

        self.graph: rdflib.Graph = rdflib.Graph()
        self.catalog: dict = {}

        with open(self.schema_file.as_posix(), 'r') as file_:
            lines = file_.readlines()
            self.iri = lines[0].split('<')[1].split('>')[0]

    def load(self):
        # load the schema into the graph
        self.graph.parse(self.schema_file.as_posix(), format='n3')
        self.graph.parse(self.soen321_file.as_posix(), format='n3')
        self.graph.parse(self.comp474_file.as_posix(), format='n3')

        self.__load_concordia_data()

        self.__generate_triples_from_catalog()
        print(f'Number of triples in the graph after loading Concordia catalog: {len(self.graph)}')

        self.__load_materials()

    def __load_concordia_data(self):
        print('Loading Concordia\'s OpenData from the configured source...')
        # read the first file CATALOG.csv, which contains more descriptive entries but doesn't have labs/tutorials/etc
        with open(self.open_data_file.as_posix(), 'r', newline='', encoding='utf-8') as file_:
            reader = csv.DictReader(file_)
            for row in reader:
                # forget courses that have no code
                if row['Course code'] == '' or row['Course number'] == '':
                    continue
                # index by courseCode-courseNumber ie SOEN-321
                self.catalog[f"{row['Course code']}-{row['Course number']}"] = row

        # read the best file
        with open(self.open_data_with_extra.as_posix(), 'r', newline='', encoding='iso-8859-1') as file_:
            reader = csv.DictReader(file_)
            id_map = {}
            for row in reader:
                # merge with existing info
                if row['Catalog'] is None:
                    # useless
                    continue

                # forget this idea for now
                # search_res = re.search('[A-Za-z]', row['Catalog'])
                # if search_res is not None:
                #     catalog = row['Catalog'][:search_res.start()]
                # else:
                #     catalog = row['Catalog']
                # idx = f'{row["Subject"]}-{catalog}'

                # recreate same idx as before
                idx = f'{row["Subject"]}-{row["Catalog"]}'
                old_row = self.catalog.get(idx, {})
                self.catalog[idx] = {**old_row, **row}
                id_map[row['Course ID']] = idx

        # read the file with the full description
        with open(self.open_data_with_desc.as_posix(), 'r', newline='', encoding='iso-8859-1') as file_:
            reader = csv.DictReader(file_)
            for row in reader:
                if row['Course ID'] not in id_map.keys():
                    continue
                # merge with existing info
                self.catalog[id_map[row['Course ID']]]['DetailedDesc'] = row['Descr']

    def __generate_triples_from_catalog(self):
        print('Generating triples from the loaded catalog...')
        # not sure the best way to go about this....
        # load up the URIs as they exist in the graph already
        course_uri, subject_rel_uri, number_uri = None, None, None
        subject_class_uri, offered_uri = None, None
        for s, _, o in self.graph:
            if course_uri is None and 'Course' in str(o) and 'vivo' in str(o):
                course_uri = o
            if subject_rel_uri is None and 'courseSubject' in str(s):
                subject_rel_uri = s
            if number_uri is None and 'courseNumber' in str(s):
                number_uri = s
            if subject_class_uri is None and 'CourseSubject' in str(s):
                subject_class_uri = s
            if offered_uri is None and 'offeredAt' in str(s):
                offered_uri = s

        # make concordia
        concordia_uri = URIRef(f'{self.iri}Concordia_University')
        self.graph.add((concordia_uri, RDF.type, URIRef('http://vivoweb.org/ontology/core#University')))
        self.graph.add((concordia_uri, RDFS.label, rdflib.Literal("Concordia University", lang='en')))
        self.graph.add((concordia_uri, OWL.sameAs, URIRef('http://dbpedia.org/resource/Concordia_University')))
        self.graph.add((concordia_uri, RDFS.comment, rdflib.Literal('This is our entry for Concordia University', lang='en')))

        # generate the triples
        subject_map = {}
        for idx, course_info in self.catalog.items():
            # forget courses that are missing some crucial info,
            # or are not the lecture component (labs, tuts, etc... that's what the re is for)
            if (
                    'Course ID' not in course_info.keys() or
                    'DetailedDesc' not in course_info.keys() or
                    'Catalog' not in course_info.keys() or
                    re.search('[A-Za-z]', course_info['Catalog']) is not None or
                    (
                        'Course number' in course_info.keys() and
                        re.search('[A-Za-z]', course_info['Course number']) is not None
                    )
            ):
                continue
            # create uri for the course
            uri = rdflib.URIRef(f'{self.iri}{course_info["Subject"]}_{course_info["Catalog"]}_course')
            # add all the triples
            self.graph.add((uri, RDF.type, course_uri))
            # create subject if it doesn't exist
            if course_info['Subject'] not in subject_map.keys():
                subj_uri = rdflib.URIRef(f'{self.iri}{course_info["Subject"]}')
                subject_map[course_info['Subject']] = subj_uri
                self.graph.add((subj_uri, RDF.type, subject_class_uri))
                self.graph.add((subj_uri, RDFS.label, rdflib.Literal(course_info["Subject"], lang='en')))
                self.graph.add((subj_uri, RDFS.comment, rdflib.Literal(course_info["Subject"], lang='en')))
            # add required fields of course
            self.graph.add((uri, subject_rel_uri, subject_map[course_info["Subject"]]))
            self.graph.add((uri, number_uri, rdflib.Literal(int(course_info["Catalog"]))))
            self.graph.add((uri, RDFS.label, rdflib.Literal(course_info["Long Title"], lang='en')))
            self.graph.add((uri, RDFS.comment, rdflib.Literal(course_info["DetailedDesc"], lang='en')))
            self.graph.add((uri, offered_uri, concordia_uri))
            if 'Website' in course_info.keys() and course_info['Website'] != '':
                # optional website
                # could also use FOAF.homepage, but i don't think all of these are homepages
                # (they come from CATALOG.csv)
                # self.graph.add((uri, FOAF.homepage, rdflib.Literal(course_info["Website"]))
                self.graph.add((uri, RDFS.seeAlso, rdflib.Literal(course_info["Website"])))

    def create_knowledge_base(self,
                              kb_format: str = 'ntriples',
                              output_location: str = None,
                              out_file: str = 'knowledge_base.n3'):
        # saves the knowledge base, default to in data folder
        if output_location is None:
            output_location = self.data_location
        # save
        file_name = os.path.join(output_location, out_file)
        print(f'Saving generated knowledge base to: {file_name}')
        self.graph.serialize(file_name, format=kb_format)


    def __parse_material_path(self, path : Path) -> dict:
        filename = path.stem

        parts = filename.split(sep="_")

        material = {'name': parts[0], 'type': parts[0], 'belongs_to':[], 'path' : path}

        if material['type'] == 'outline':
            material['type'] = 'LectureMaterial'

        # get all the lecture/tutorial/etc numbers this material is for
        if len(parts) > 1:
            material['belongs_to'] = [idx.split('-')[0] for idx in parts[1:]]

        return material

    def __get_events_by_number(self, numbers : list, eventType : str, course : dict) -> list:
        # gets the lectures 
        query = f"""
            SELECT DISTINCT ?event
            WHERE {{
                ?course 
                    concc:courseNumber {course['number']};
                    concc:courseSubject concc:{course['subject'].upper()};
                .
                ?event 
                    concc:lectureNumber ?n;
                    a concc:{eventType};
                    (concc:lectureFor|concc:tutorialFor|concc:labFor)+ ?course;
                .

                FILTER (
                    {
                        " || ".join([f"?n = {i}" for i in numbers])
                    }
                )

            }}
            """
        res = self.graph.query(query, initNs={'concc':rdflib.Namespace(self.iri)})

        events = []
        for row in res:
            events.append(row[0])

        return events

    
    def __connect_material(self, mat : dict, course : dict, parent_uri : rdflib.URIRef = None,  parentType : str = None):
        # get fileURI for absolute path
        file_URI = mat['path'].resolve().as_uri()
        file_URI = rdflib.URIRef(file_URI)
        # create entry for this instance
        self.graph.add((file_URI, RDF.type, rdflib.URIRef(f"{self.iri}{mat['type'].capitalize()}")))

        # create triple bridging material and what it belongs to
        if not mat['belongs_to']: # if the list is empty, it belongs to the course itself
            prop = rdflib.URIRef(f"{self.iri}materialFor")

            self.graph.add((file_URI, prop, parent_uri))
            self.graph.add((file_URI, RDFS.label, rdflib.Literal(f"{mat['name']} for {course['subject']}-{course['number']}")))

        else:   # otherwise, the material belongs to some amount of events
            prop = rdflib.URIRef(f"{self.iri}lectureMaterialFor")
            events = self.__get_events_by_number(mat['belongs_to'], parentType, course)

            for event in events:
                self.graph.add((file_URI, prop, event))

            self.graph.add((file_URI, RDFS.label, rdflib.Literal(f"{mat['name']} for {course['subject']}-{course['number']} {parentType}(s): {', '.join(mat['belongs_to'])}")))


    # make triple for class of mat, make triple(s) for property conection of mat 
    def __load_materials(self):
        # path to material folder
        matPath = self.data_location / 'material'

        # iterate over classes
        for classPath in matPath.iterdir():
            # get class name
            name = classPath.name
            match = re.match('(\D*)(\d*)', name)
            course = {'subject': match.group(1), 'number': match.group(2)}

            # iterate over the types of content
            for courseContent in classPath.iterdir():
                # construct URI for the course
                course_uri = rdflib.URIRef(f"{self.iri}{course['subject'].upper()}_{course['number']}_course")

                if courseContent.is_file():
                   parsed_mat = self.__parse_material_path(courseContent)
                   self.__connect_material(parsed_mat, course, parent_uri=course_uri)

                else:
                    parentType = courseContent.stem.capitalize()

                    for materialPath in  courseContent.iterdir():
                        material = self.__parse_material_path(materialPath)
                        self.__connect_material(material, course, parentType=parentType)

