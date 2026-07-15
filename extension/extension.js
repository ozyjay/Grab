import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Shell from 'gi://Shell';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';

const GrabIndicator = GObject.registerClass(
class GrabIndicator extends PanelMenu.Button {
    _init(helperPath) {
        super._init(0.0, 'Grab Screenshot', true);

        this._helperPath = helperPath;
        this.add_child(new St.Icon({
            icon_name: 'camera-photo-symbolic',
            style_class: 'system-status-icon',
        }));
    }

    _launch(...arguments_) {
        try {
            Gio.Subprocess.new(
                [this._helperPath, ...arguments_],
                Gio.SubprocessFlags.NONE);
            return true;
        } catch (error) {
            Main.notify(
                'Grab could not start',
                error instanceof Error ? error.message : String(error));
            return false;
        }
    }

    _capture() {
        if (this._captureInProgress)
            return;

        this._captureInProgress = true;
        const filename = `grab-${GLib.uuid_string_random()}.png`;
        const path = GLib.build_filenamev([
            GLib.get_user_runtime_dir(),
            filename,
        ]);
        const file = Gio.File.new_for_path(path);
        let stream;

        try {
            stream = file.create(Gio.FileCreateFlags.PRIVATE, null);
            const screenshot = new Shell.Screenshot();
            screenshot.screenshot(false, stream, (source, result) => {
                try {
                    source.screenshot_finish(result);
                    stream.close(null);
                    const [bytes] = file.load_bytes(null);
                    St.Clipboard.get_default().set_content(
                        St.ClipboardType.CLIPBOARD,
                        'image/png',
                        bytes);
                    if (!this._launch('--capture-file', path))
                        file.delete_async(GLib.PRIORITY_DEFAULT, null, null);
                } catch (error) {
                    try {
                        stream.close(null);
                    } catch (_closeError) {
                        // The original capture error is more useful.
                    }
                    file.delete_async(GLib.PRIORITY_DEFAULT, null, null);
                    Main.notify(
                        'Grab could not take a screenshot',
                        error instanceof Error ? error.message : String(error));
                } finally {
                    this._captureInProgress = false;
                }
            });
        } catch (error) {
            this._captureInProgress = false;
            Main.notify(
                'Grab could not take a screenshot',
                error instanceof Error ? error.message : String(error));
        }
    }

    vfunc_button_press_event(event) {
        switch (event.get_button()) {
        case Clutter.BUTTON_PRIMARY:
            this._capture();
            return Clutter.EVENT_STOP;
        case Clutter.BUTTON_SECONDARY:
            this._launch('--preferences');
            return Clutter.EVENT_STOP;
        default:
            return super.vfunc_button_press_event(event);
        }
    }

    vfunc_key_release_event(event) {
        const symbol = event.get_key_symbol();
        if (symbol === Clutter.KEY_Return ||
            symbol === Clutter.KEY_KP_Enter ||
            symbol === Clutter.KEY_space) {
            this._capture();
            return Clutter.EVENT_STOP;
        }

        return super.vfunc_key_release_event(event);
    }
});

export default class GrabExtension extends Extension {
    enable() {
        const helperPath = GLib.build_filenamev([
            GLib.get_user_data_dir(),
            'org.grabtool.Grab',
            'grab',
        ]);

        this._indicator = new GrabIndicator(helperPath);
        Main.panel.addToStatusArea('grab-screenshot', this._indicator, 0, 'right');
    }

    disable() {
        this._indicator?.destroy();
        this._indicator = null;
    }
}
