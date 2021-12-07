import sys
import json
import os
import subprocess
import re
from datetime import datetime
from pprint import pprint
from bs4 import BeautifulSoup
from chardet import detect
import pandas as pd

SEARCH_STR_CMD = 'pt' #TODO: Replace with a commonly available command
BASE_DIR = os.path.abspath('.')


class UnusedImageChecker:
    site_dir = None
    img_exts = []
    img_infos = []
    unused_imgs = []
    unknown_imgs = []
    unread_files = []
    saved_file_name = None
    output_format = 'json'
    dev_mode = False


    def __init__(self, site_dir, output_format='json', is_debug_mode=False):
        print('Start')
        self.site_dir = site_dir
        self.img_exts = ['jpeg', 'jpg', 'png', 'gif', 'svg']
        self.output_format = output_format
        self.dev_mode = is_debug_mode


    def __del__(self):
        print('End')


    def init(self):
        pass


    def execute(self):
        print('1. Save image paths')
        self.set_img_infos()
        self.check_imgs_used()
        res = {
            'unused': self.unused_imgs,
            'unknown': self.unknown_imgs,
            'unread': self.unread_files,
        }
        saved_path = self.save_result(res)
        if self.output_format == 'csv':
            saved_path = self.convert2csv(saved_path)

        if self.dev_mode:
            pprint(res)

        print(saved_path)


    def check_imgs_used(self):
        for idx, info in enumerate(self.img_infos):
            if not info['exists_searched']:
                continue

            is_exists = False
            for path in info['searched_paths']:
                exists = self.check_exists_in_target_file(info['root_path'], path)
                if exists:
                    is_exists = True
                    self.img_infos[idx]['is_used'] = True
                    break

            if not is_exists:
                self.img_infos[idx]['is_used'] = False
                self.unused_imgs.append(info['root_path'])


    def check_exists_in_target_file(self, img_root_path, target_root_path):
        ext = os.path.splitext(target_root_path)[1]
        if ext in ['.htm', '.html']:
            return self.check_exists_in_target_html(img_root_path, target_root_path)

        if ext == '.css':
            return self.check_exists_in_target_css(img_root_path, target_root_path)

        self.unknown_imgs.append({
            'img': img_root_path,
            'target': target_root_path,
            'note': 'Not applicable file format',
        })
        return False


    def check_exists_in_target_html(self, img_root_path, target_file_root_path):
        target_file_abs_path = self.site_dir + target_file_root_path.replace('./', '/')
        img_abs_path = self.site_dir + img_root_path
        dir_abs_path = os.path.dirname(target_file_abs_path)
        data = None
        try:
            data = self.file_read(target_file_abs_path)
        except UnicodeDecodeError:
            unread_file = {
                'img': img_root_path,
                'target': target_file_root_path,
                'note': 'Error: UnicodeDecodeError',
            }
            self.unread_files.append(unread_file)

        if not data:
            return False

        soup = BeautifulSoup(data, 'html.parser')
        img_tags = soup.find_all('img')
        is_exists = False
        for img_tag in img_tags:
            if is_exists:
                break

            src = img_tag['src']
            if src.startswith('/'):
                if src == img_root_path:
                    is_exists = True
            else:
                os.chdir(dir_abs_path)
                src_abs = os.path.abspath(src)
                if src_abs == img_abs_path:
                    is_exists = True

        return is_exists


    def check_exists_in_target_css(self, img_root_path, target_file_root_path):
        target_file_abs_path = self.site_dir + target_file_root_path.replace('./', '/')
        img_abs_path = self.site_dir + img_root_path
        dir_abs_path = os.path.dirname(target_file_abs_path)

        with open(target_file_abs_path,'r') as f:
            readed = f.read()

        is_exists = False
        check_img_paths = re.findall(r'url\(\'?([^\^\')]+)\'?\)', readed)
        for check_img_path in check_img_paths:
            if is_exists:
                break

            if check_img_path.startswith('/'):
                if check_img_path == img_root_path:
                    is_exists = True
            else:
                os.chdir(dir_abs_path)
                check_img_path_abs = os.path.abspath(check_img_path)
                if check_img_path_abs == img_abs_path:
                    is_exists = True

        return is_exists


    def set_img_infos(self):
        #find public -name \*.png -or -name \*.jpg -or -name \*.jpeg -or -name \*.gif
        cmds = [
            'find',
            self.site_dir,
        ]
        exts = ['-name *.%s' % e for e in self.img_exts]
        conds = ' -or '.join(exts).split(' ')
        cmds.extend(conds)
        img_paths = sorted(self.exec_cmd(cmds).splitlines())
        if self.dev_mode:
            img_paths = img_paths[0:50]
        self.img_infos = [self.get_img_info_by_path(img_path) for img_path in img_paths]


    def get_img_info_by_path(self, abs_path):
        res = {'abs_path':abs_path}
        root_path = abs_path.replace(self.site_dir, '')
        file_name = os.path.basename(root_path)
        res['root_path'] = root_path
        res['file_name'] = file_name
        cmds = [
            SEARCH_STR_CMD,
            '-l',
            file_name,
        ]
        searched_paths = sorted(self.exec_cmd(cmds, self.site_dir).splitlines())
        res['searched_paths'] = searched_paths
        res['exists_searched'] = bool(len(searched_paths))

        if not searched_paths:
            res['is_used'] = False
            self.unused_imgs.append(root_path)

        return res


    @staticmethod
    def load_json_as_df(path):
        ret = []
        ret.append(['Type', 'Image', 'TargetFile', 'Note'])
        with open(path) as jsonfile:
            res = json.load(jsonfile)

        for res_type, items in res.items():
            if not items:
                continue

            for item in items:
                note = item.get('note', '')
                if res_type == 'unused':
                    ret.append([res_type, item, '', note])
                elif res_type == 'unread':
                    ret.append([res_type, item['img'], item['target'], note])
                elif res_type == 'unknown':
                    ret.append([res_type, item['img'], item['target'], note])
        return ret


    def convert2csv(self, path):
        #Read json
        items = self.load_json_as_df(path)
        df = pd.DataFrame(items)
        if self.dev_mode:
            print(df)
        res_path = self.result_file_path('csv')
        df.to_csv(res_path, header=False, index=False)
        return res_path


    def result_file_path(self, ext='json'):
        if not self.saved_file_name:
            self.saved_file_name = datetime.now().strftime('%Y%m%d%H%M%S')
        return '%s/var/%s.%s' % (BASE_DIR, self.saved_file_name, ext)


    def save_result(self, body):
        path = self.result_file_path()
        self.save_json(path, body)
        return path


    @staticmethod
    def save_json(file_path, body):
        with open(file_path, mode='w') as fp:
            json.dump(body, fp, indent=2)


    @staticmethod
    def file_read(path):
        with open(path, 'rb') as f:
            b = f.read()
        enc = detect(b)

        with open(path, encoding=enc['encoding']) as f:
            s = f.read()

        return s


    @staticmethod
    def exec_cmd(items, cwd='./'):
        state = subprocess.run(
            items,
            stdout=subprocess.PIPE,
            cwd=cwd,
            check=True
        )
        return state.stdout.decode('utf8').strip()


def main(path, output_format = 'json', is_debug_mode=False):
    ins = UnusedImageChecker(path, output_format, is_debug_mode)
    ins.execute()


if __name__ == "__main__":
    is_conv_csv = False
    is_debug = False
    args = sys.argv
    if len(args) < 2:
        print('Arguments are too short')
    elif len(args) > 4:
        print('Arguments are too long')
    elif len(args) == 3:
        is_conv_csv = bool(args[2])
    elif len(args) == 4:
        is_conv_csv = bool(args[2])
        is_debug = bool(args[3])
    target_path = args[1]
    res_format = 'csv' if is_conv_csv else 'json'
    main(target_path, res_format, is_debug)
