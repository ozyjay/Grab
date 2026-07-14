import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';

const GrabIndicator = GObject.registerClass(
class GrabIndicator extends PanelMenu.Button {
    constructor(helperPath) {
        super(0.0, 'Grab Screenshot', false);

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
        } catch (error) {
            Main.notify(
                'Grab could not start',
                error instanceof Error ? error.message : String(error));
        }
    }

    vfunc_button_press_event(event) {
        switch (event.get_button()) {
        case Clutter.BUTTON_PRIMARY:
            this._launch();
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
            this._launch();
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
