import json
import pathlib
import logging
import requests
import datetime
import sd_payloads

from integrations.SD_Lon.sd_common import sd_lookup
from os2mo_helpers.mora_helpers import MoraHelper
from integrations.SD_Lon.exceptions import NoCurrentValdityException

# LOG_LEVEL = logging.DEBUG
# LOG_FILE = 'fix_sd_departments.log'

logger = logging.getLogger('fixDepartments')

# detail_logging = ('sdCommon', 'fixDepartments')
# for name in logging.root.manager.loggerDict:
#     if name in detail_logging:
#         logging.getLogger(name).setLevel(LOG_LEVEL)
#     else:
#         logging.getLogger(name).setLevel(logging.ERROR)

# logging.basicConfig(
#     format='%(levelname)s %(asctime)s %(name)s %(message)s',
#     level=LOG_LEVEL,
#     filename=LOG_FILE
# )


class FixDepartments(object):
    def __init__(self):
        logger.info('Start program')
        # TODO: Soon we have done this 4 times. Should we make a small settings
        # importer, that will also handle datatype for specicic keys?
        cfg_file = pathlib.Path.cwd() / 'settings' / 'settings.json'
        if not cfg_file.is_file():
            raise Exception('No setting file')
        self.settings = json.loads(cfg_file.read_text())

        self.institution_uuid = self.get_institution()
        self.helper = MoraHelper(hostname=self.settings['mora.base'],
                                 use_cache=False)

        try:
            self.org_uuid = self.helper.read_organisation()
        except requests.exceptions.RequestException as e:
            logger.error(e)
            print(e)
            exit()

        logger.info('Read org_unit types')
        self.unit_types = self.helper.read_classes_in_facet('org_unit_type')[0]

    # def create_department(self, department, activation_date):
    #     params = {
    #         'ActivationDate': activation_date,
    #         'DeactivationDate': activation_date,
    #         'DepartmentIdentifier': department['DepartmentIdentifier'],
    #         'ContactInformationIndicator': 'true',
    #         'DepartmentNameIndicator': 'true',
    #         'PostalAddressIndicator': 'false',
    #         'ProductionUnitIndicator': 'false',
    #         'UUIDIndicator': 'true',
    #         'EmploymentDepartmentIndicator': 'false'
    #     }
    #     department_info = sd_lookup('GetDepartment20111201', params)

    #     for unit_type in self.unit_types:
    #         if unit_type['user_key'] == department['DepartmentLevelIdentifier']:
    #             unit_type_uuid = unit_type['uuid']

    #     payload = sd_payloads.create_org_unit(
    #         department=department,
    #         org=self.org_uuid,
    #         name=department_info['Department']['DepartmentName'],
    #         unit_type=unit_type_uuid,
    #         from_date=department_info['Department']['ActivationDate']
    #     )
    #     logger.debug('Create department payload: {}'.format(payload))

    #     response = self.helper._mo_post('ou/create', payload)
    #     response.raise_for_status()
    #     logger.info('Created unit {}'.format(
    #         department['DepartmentIdentifier'])
    #     )
    #     logger.debug('Response: {}'.format(response.text))

    # def fix_departments(self):
    #     params = {
    #         'ActivationDate': self.from_date.strftime('%d.%m.%Y'),
    #         'DeactivationDate': '31.12.9999',
    #         'UUIDIndicator': 'true'
    #     }
    #     # TODO: We need to read this without caching!
    #     organisation = sd_lookup('GetOrganization20111201', params)
    #     department_lists = organisation['Organization']
    #     if not isinstance(department_lists, list):
    #         department_lists = [department_lists]

    #     total = 0
    #     checked = 0
    #     for department_list in department_lists:
    #         departments = department_list['DepartmentReference']
    #         total += len(departments)

    #     logger.info('Checking {} departments'.format(total))
    #     for department_list in department_lists:
    #         # All units in this list has same activation date
    #         activation_date = department_list['ActivationDate']

    #         departments = department_list['DepartmentReference']
    #         for department in departments:
    #             checked += 1
    #            print('{}/{} {:.2f}%'.format(checked, total, 100.0 * checked/total))
    #             departments = []
    #             uuid = department['DepartmentUUIDIdentifier']
    #             ou = self.helper.read_ou(uuid)
    #             logger.debug('Check for {}'.format(uuid))

    #             if 'status' in ou:  # Unit does not exist
    #                 print('klaf')
    #                 departments.append(department)
    #                 logger.info('{} is new in MO'.format(uuid))
    #                 parent_department = department
    #                 while 'DepartmentReference' in parent_department:
    #                    parent_department = parent_department['DepartmentReference']
    #                     parent_uuid = parent_department['DepartmentUUIDIdentifier']
    #                     ou = self.helper.read_ou(parent_uuid)
    #                     logger.debug('Check for {}'.format(parent_uuid))
    #                     if 'status' in ou:  # Unit does not exist
    #                         logger.info('{} is new in MO'.format(parent_uuid))
    #                         departments.append(parent_department)

    #             # Create actual departments
    #             while departments:
    #                 self.create_department(departments.pop(), activation_date)

    def get_institution(self):
        inst_id = self.settings['integrations.SD_Lon.institution_identifier']
        params = {
            'UUIDIndicator': 'true',
            'InstitutionIdentifier': inst_id
        }
        institution_info = sd_lookup('GetInstitution20111201', params)
        # print(institution_info.keys())
        institution = institution_info['Region']['Institution']
        institution_uuid = institution['InstitutionUUIDIdentifier']
        return institution_uuid

    def create_single_department(self, unit_uuid, validity_date):
        """ Create a single department at a single snapshot in time """
        logger.info('Create department: {}, at {}'.format(unit_uuid, validity_date))
        validity = {
            'from_date': validity_date.strftime('%d.%m.%Y'),
            'to_date': validity_date.strftime('%d.%m.%Y')
        }
        # We ask for a single date, and will always get a single element
        department = self.get_department(validity, uuid=unit_uuid)[0]
        logger.debug('Department info to create from: {}'.format(department))
        print('Department info to create from: {}'.format(department))
        parent = self.get_parent(department['DepartmentUUIDIdentifier'],
                                 validity_date)
        if parent is None:
            parent = self.org_uuid

        for unit_type in self.unit_types:
            if unit_type['user_key'] == department['DepartmentLevelIdentifier']:
                unit_type_uuid = unit_type['uuid']

        payload = sd_payloads.create_single_org_unit(
            department=department,
            unit_type=unit_type_uuid,
            parent=parent
        )
        logger.debug('Create department payload: {}'.format(payload))
        response = self.helper._mo_post('ou/create', payload)
        response.raise_for_status()
        logger.info('Created unit {}'.format(
            department['DepartmentIdentifier'])
        )
        logger.debug('Response: {}'.format(response.text))

    def fix_specific_department(self, shortname):
        """
        Run through historic information from SD and attempt to replicate
        this in MO. Departments will not be created, so the existence in MO
        mus be confirmed by other means.
        """
        # Semi-arbitrary start date for historic import
        from_date = datetime.datetime(2000, 1, 1, 0, 0)
        logger.info('Fix import of department {}'.format(shortname))

        params = {
            'ActivationDate': from_date.strftime('%d.%m.%Y'),
            'DeactivationDate': '9999-12-31',
            'DepartmentIdentifier': shortname,
            'UUIDIndicator': 'true',
            'DepartmentNameIndicator': 'true'
        }

        department = sd_lookup('GetDepartment20111201', params, use_cache=False)
        validities = department['Department']
        if isinstance(validities, dict):
            validities = [validities]

        first_iteration = True
        for validity in validities:
            assert shortname == validity['DepartmentIdentifier']
            validity_date = datetime.datetime.strptime(validity['ActivationDate'],
                                                       '%Y-%m-%d')
            user_key = shortname
            name = validity['DepartmentName']
            unit_uuid = validity['DepartmentUUIDIdentifier']

            for unit_type in self.unit_types:
                if unit_type['user_key'] == validity['DepartmentLevelIdentifier']:
                    unit_type_uuid = unit_type['uuid']

            # SD has a challenge with the internal validity-consistency, extend first
            # validity indefinitely
            if first_iteration:
                from_date = '1900-01-01'
                first_iteration = False
            else:
                from_date = validity_date.strftime('%Y-%m-%d')

            try:
                parent = self.get_parent(unit_uuid, datetime.datetime.now())
            except NoCurrentValdityException:
                print('Error')
                parent = self.settings[
                    'integrations.SD_Lon.unknown_parent_container'
                ]
            print('Unit parent at {} is {}'.format(from_date, parent))

            payload = sd_payloads.edit_org_unit(user_key, name, unit_uuid, parent,
                                                unit_type_uuid, from_date)
            logger.debug('Edit payload to fix unit: {}'.format(payload))
            response = self.helper._mo_post('details/edit', payload)
            if response.status_code == 400:
                assert(response.text.find('raise to a new registration') > 0)
            else:
                response.raise_for_status()
            logger.debug('Response: {}'.format(response.text))

    def fix_department_at_single_date(self, unit_uuid, validity_date):
        logger.info('Set department {} to state as of today'.format(unit_uuid))
        validity = {
            'from_date': validity_date.strftime('%d.%m.%Y'),
            'to_date': validity_date.strftime('%d.%m.%Y')
        }
        department = self.get_department(validity, uuid=unit_uuid)[0]

        for unit_type in self.unit_types:
            if unit_type['user_key'] == department['DepartmentLevelIdentifier']:
                unit_type_uuid = unit_type['uuid']

        try:
            parent = self.get_parent(unit_uuid, validity_date)
            department = self.get_department(validity, uuid=unit_uuid)[0]
            name = department['DepartmentName']
            shortname = department['DepartmentIdentifier']
        except NoCurrentValdityException:
            msg = 'Attempting to fix unit with no parent at {}!'
            logger.error(msg.format(validity_date))
            raise Exception(msg.format(validity_date))

        # SD has a challenge with the internal validity-consistency, extend first
        # validity indefinitely
        from_date = '1900-01-01'
        if parent is None:
            parent = self.org_uuid
        print('Unit parent at {} is {}'.format(from_date, parent))

        payload = sd_payloads.edit_org_unit(shortname, name, unit_uuid, parent,
                                            unit_type_uuid, from_date)
        logger.debug('Edit payload to fix unit: {}'.format(payload))
        response = self.helper._mo_post('details/edit', payload)
        if response.status_code == 400:
            assert(response.text.find('raise to a new registration') > 0)
        else:
            response.raise_for_status()
        logger.debug('Response: {}'.format(response.text))

    def get_department(self, validity, shortname=None, uuid=None):
        """
        Read department information from SD.
        NOTICE: Shortname is not universally unitque in SD, and even a request
        spanning a single date might return more than one row if searched by
        shortname.
        :param validity: Validity dictionaty containing two datetime objects
        with keys from_date and to_date.
        :param shortname: Shortname for the unit(s).
        :param uuid: uuid for the unit.
        :return: A list of information about the unit(s).
        """
        params = {
            'ActivationDate': validity['from_date'],
            'DeactivationDate': validity['to_date'],
            'ContactInformationIndicator': 'true',
            'DepartmentNameIndicator': 'true',
            'PostalAddressIndicator': 'false',
            'ProductionUnitIndicator': 'false',
            'UUIDIndicator': 'true',
            'EmploymentDepartmentIndicator': 'false'
        }
        if uuid is not None:
            params['DepartmentUUIDIdentifier'] = uuid
        if shortname is not None:
            params['DepartmentIdentifier'] = shortname

        if uuid is None and shortname is None:
            raise Exception('Provide either uuid or shortname')

        department_info = sd_lookup('GetDepartment20111201', params)
        department = department_info.get('Department')
        if department is None:
            raise NoCurrentValdityException()
        if isinstance(department, dict):
            department = [department]
        return department

    def get_parent(self, unit_uuid, validity_date):
        params = {
            'EffectiveDate': validity_date.strftime('%d.%m.%Y'),
            'DepartmentUUIDIdentifier': unit_uuid
        }
        parent_response = sd_lookup('GetDepartmentParent20190701', params)
        if 'DepartmentParent' not in parent_response:
            msg = 'No parent for {} found at validity: {}'
            logger.error(msg.format(unit_uuid, validity_date))
            raise NoCurrentValdityException()
        parent = parent_response['DepartmentParent']['DepartmentUUIDIdentifier']
        if parent == self.institution_uuid:
            parent = None
        return parent

    def get_all_parents(self, leaf_uuid, validity_date):
        validity = {
            'from_date': validity_date.strftime('%d.%m.%Y'),
            'to_date': validity_date.strftime('%d.%m.%Y')
        }
        department_branch = []
        department = self.get_department(validity=validity, uuid=leaf_uuid)[0]
        department_branch.append((department['DepartmentIdentifier'], leaf_uuid))

        current_uuid = self.get_parent(department['DepartmentUUIDIdentifier'],
                                       validity_date=validity_date)

        while current_uuid is not None:
            current_uuid = self.get_parent(department['DepartmentUUIDIdentifier'],
                                           validity_date=validity_date)
            department = self.get_department(validity=validity, uuid=current_uuid)[0]
            shortname = department['DepartmentIdentifier']
            level = department['DepartmentLevelIdentifier']
            uuid = department['DepartmentUUIDIdentifier']
            department_branch.append((shortname, uuid))
            current_uuid = self.get_parent(current_uuid, validity_date=validity_date)
            msg = 'Department: {}, uuid: {}, level: {}'
            logger.debug(msg.format(shortname, uuid, level))
        return department_branch

    def fix_or_create_branch(self, leaf_uuid, date):
        # This is a question to SD, units will not need to exist in MO
        branch = self.get_all_parents(leaf_uuid, date)

        for unit in branch:
            mo_unit = self.helper.read_ou(unit[1])
            if 'status' in mo_unit:  # Unit does not exist in MO
                logger.warning('Unknown unit {}, will create'.format(unit))
                self.create_single_department(unit[1], date)
        for unit in reversed(branch):
            self.fix_department_at_single_date(unit[1], date)


if __name__ == '__main__':
    unit_fixer = FixDepartments()
    uruk = 'cf9864bf-1ed8-4800-9600-000001290002'

    # from_date = datetime.datetime(2008, 8, 1, 0, 0)
    # print(unit_fixer.get_all_parents(uruk, from_date))

    today = datetime.datetime.today()
    # print(unit_fixer.get_all_parents(uruk, today))
    unit_fixer.fix_or_create_branch(uruk, today)