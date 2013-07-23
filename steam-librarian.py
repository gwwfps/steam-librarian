import platform
import winreg
import sys
import glob
import os.path
import re
import io
import shutil


sys.stdout = io.TextIOWrapper(sys.stdout.buffer,encoding='utf8')


def get_steam_path():
    reg_software_root = 'SOFTWARE\Wow6432Node\\' if platform.architecture()[0] == '64bit' else 'SOFTWARE\\'
    steam_key_subpath = reg_software_root + 'Valve\Steam'
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, steam_key_subpath) as key:
            return winreg.QueryValueEx(key, 'InstallPath')[0]
    except OSError:
        return None


def find_value(file_content, value_name):
    exp = re.compile('"{}"\s+"(.+)"'.format(value_name))
    match = exp.search(file_content)
    if match is None:
        return None
    else:
        return match.group(1)


def search_library_paths(config):
    i = 1
    while True:
        value = find_value(config, 'BaseInstallFolder_{:d}'.format(i))
        if value is None:
            return
        else:
            yield os.path.normpath(value)
        i += 1


def get_library_paths(steam_path):
    with open(os.path.join(steam_path, 'config\config.vdf'), encoding='utf-8') as config_file:
        config = config_file.read()
        return [steam_path] + [path for path in search_library_paths(config)]


def print_library_paths(library_paths):
    print("Steam libraries:")
    for i, path in enumerate(library_paths):
        print("  {:d}: {}".format(i, path))


def print_help(commands):
    print("steam-librarian - a utility for moving games between Steam libraries, do not use while Steam is running")
    print("Available commands:")
    max_command_len = max(len(command.help[0]) for command in commands)
    for command in commands:
        print("  {}:{}{}".format(command.help[0],
                                 " " * (max_command_len - len(command.help[0]) + 1),
                                 command.help[1]))


def get_game_ids(index, library_paths):
    if index < len(library_paths):
        lib_path = library_paths[index]
        steamapps_dir = os.path.join(lib_path, 'steamapps')
        appmanifest_prefix = os.path.join(steamapps_dir, 'appmanifest_')

        game_ids = []
        
        for file in glob.glob(appmanifest_prefix + '*.acf'):
            try:
                game_ids.append(int(file[len(appmanifest_prefix):len(file)-4]))
            except ValueError:
                pass

        return game_ids
    else:
        error("No such library.")


def get_game(steamapps_path, game_id):
    with open(os.path.join(steamapps_path, 'appmanifest_{:d}.acf'.format(game_id)), encoding='utf-8') as manifest:
        manifest_content = manifest.read()        
        app_id = find_value(manifest_content, 'appID')
        if app_id and int(app_id) == game_id:
            name = find_value(manifest_content, 'name')
            install_dir = find_value(manifest_content, 'installdir')
            if name and install_dir:                    
                return (game_id, name, os.path.basename(install_dir))


def get_games(index, library_paths):
    game_ids = get_game_ids(index, library_paths)
    steamapps_path = os.path.join(library_paths[index], 'steamapps')   
    games = [get_game(steamapps_path, id) for id in game_ids]
    return [game for game in games if game is not None]


def print_games_in_library(index, library_paths):
    print("Games in library {:d}:".format(index))
    for id, dir, _ in sorted(get_games(index, library_paths), key=lambda p: p[1]):
        print("  {:d}: {}".format(id, dir))


def move_game(game_id, index, library_paths):
    target_lib_game_ids = get_game_ids(index, library_paths)
    if game_id in target_lib_game_ids:
        error("The specified game is already in the target library.")
        return

    for i, library_path in enumerate(library_paths):
        if not i == index:
            game_ids = get_game_ids(i, library_paths)
            if game_id in game_ids:
                steamapps_path = os.path.join(library_path, 'steamapps')
                game_id, name, install_dir = get_game(steamapps_path, game_id)
                
                print("Game to move: {}".format(name))
                print("From: {}".format(library_path))
                print("To: {}".format(library_paths[index]))

                if input("Ready? (y/N) ").lower() == 'y':
                    target_steamapps = os.path.join(library_paths[index], 'steamapps')
                    print("Moving, do not interrupt...")
                    sys.stdout.flush()
                    shutil.move(os.path.join(steamapps_path, 'common', install_dir),
                                os.path.join(target_steamapps, 'common'))
                    shutil.move(os.path.join(steamapps_path, 'appmanifest_{:d}.acf'.format(game_id)),
                                target_steamapps)
                    print("Done.")
                break
    else:
        error("Cannot find game in any library.")
        return
             

available_commands = []
class Command(object):
    def __init__(self, pattern, func, help, arg_processors=None, additional_args=None):
        self.exp = re.compile(pattern + "\Z")
        self.func = func
        self.help = help
        self.arg_processors = arg_processors
        self.additional_args = additional_args
        available_commands.append(self)

    def dispatch(self, command):
        match = self.exp.match(command)
        if match:
            args = []
            if self.arg_processors:
                for arg, processor in zip(match.groups(), self.arg_processors):
                    args.append(processor(arg))
            else:
                if match.groups():
                    for group in match.groups():
                        args.append(group)

            if self.additional_args:
                args += self.additional_args

            self.func(*args)
            return True
        else:
            return False


def error(message):
    print(message, file=sys.stderr)


def fail(message):
    error(message)
    sys.exit(1)


if __name__ == '__main__':
    steam_path = get_steam_path()
    if steam_path is None:
        fail("Cannot find Steam install location.")
        
    library_paths = get_library_paths(steam_path)
        
    Command("list", print_library_paths,
            ("list", "list all Steam libraries and their indices"), 
            additional_args=[library_paths])
    Command("list (\d)", print_games_in_library,
            ("list <lib_index>", "list all games installed in the specified library"),
            arg_processors=[int], additional_args=[library_paths])
    Command("move (\d+) (\d+)", move_game,
            ("move <game_id> <lib_index>", "move the specified game to the specific library"),
            arg_processors=[int, int], additional_args=[library_paths])
    Command("help", print_help,
            ("help", "display this message again"),
            additional_args=[available_commands])
    Command("exit", sys.exit,
            ("exit", "exit the program"))

    print_help(available_commands)
    print_library_paths(library_paths)

    while True:        
        command = input("> ").strip()
        
        library_paths.clear()
        library_paths.extend(get_library_paths(steam_path))

        for available_command in available_commands:
            if available_command.dispatch(command):
                break
        else:
            print("Unknown command.")    


