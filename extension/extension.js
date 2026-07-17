import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Shell from 'gi://Shell';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as ModalDialog from 'resource:///org/gnome/shell/ui/modalDialog.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import {
    MAX_CUSTOM_DURATION,
    MIN_CUSTOM_DURATION,
    parseDuration,
} from './duration.js';

const SCREENCAST_BUS = 'org.gnome.Shell.Screencast';
const SCREENCAST_PATH = '/org/gnome/Shell/Screencast';
const SCREENCAST_INTERFACE = 'org.gnome.Shell.Screencast';
const RECORDING_DURATIONS = [5, 10, 15, 30, 60];
const CAPTURE_DELAY_MS = 200;

const DurationDialog = GObject.registerClass(
class DurationDialog extends ModalDialog.ModalDialog {
    _init(initialDuration, record) {
        super._init();
        this._record = record;

        const title = new St.Label({
            text: 'Record an animated GIF',
            style_class: 'headline',
        });
        this.contentLayout.add_child(title);
        const description = new St.Label({
            text: `Duration in seconds (${MIN_CUSTOM_DURATION}–${MAX_CUSTOM_DURATION})`,
        });
        this.contentLayout.add_child(description);
        this._entry = new St.Entry({
            text: String(initialDuration),
            can_focus: true,
            x_expand: true,
        });
        this._entry.clutter_text.set_input_purpose(Clutter.InputContentPurpose.DIGITS);
        this._entry.clutter_text.connect('text-changed', () => this._validate());
        this.contentLayout.add_child(this._entry);
        this._error = new St.Label({
            text: '',
            style_class: 'error-label',
        });
        this.contentLayout.add_child(this._error);

        this.addButton({
            label: 'Cancel',
            action: () => this.close(),
            key: Clutter.KEY_Escape,
        });
        this._recordButton = this.addButton({
            label: 'Record',
            action: () => this._submit(),
            default: true,
        });
        this.setInitialKeyFocus(this._entry);
        this.connect('opened', () => {
            this._entry.clutter_text.set_selection(0, -1);
        });
        this._validate();
    }

    _duration() {
        return parseDuration(this._entry.get_text());
    }

    _validate() {
        const valid = this._duration() !== null;
        this._recordButton.reactive = valid;
        this._recordButton.can_focus = valid;
        this._error.text = valid
            ? ''
            : `Enter a whole number from ${MIN_CUSTOM_DURATION} to ${MAX_CUSTOM_DURATION}.`;
    }

    _submit() {
        const duration = this._duration();
        if (duration === null)
            return;
        this.close();
        this._record(duration);
    }

});

const GrabIndicator = GObject.registerClass(
class GrabIndicator extends PanelMenu.Button {
    _init(helperPath) {
        super._init(0.0, 'Grab', false);

        this._helperPath = helperPath;
        this._recordingPath = null;
        this._recordingDuration = 0;
        this._remaining = 0;
        this._timerId = 0;
        this._stopping = false;
        this._customDuration = 30;
        this._durationDialog = null;
        this._destroying = false;
        this._captureInProgress = false;
        this._captureTimeoutId = 0;
        this._cancellable = new Gio.Cancellable();
        this._screencast = null;
        this._errorSignal = 0;
        this._icon = new St.Icon({
            icon_name: 'camera-photo-symbolic',
            style_class: 'system-status-icon',
        });
        this.add_child(this._icon);

        this.menu.addAction('Take Screenshot', () => this._capture());
        const recordingMenu = new PopupMenu.PopupSubMenuMenuItem('Record GIF');
        for (const duration of RECORDING_DURATIONS) {
            recordingMenu.menu.addAction(
                `${duration} seconds`,
                () => this._startRecording(duration));
        }
        recordingMenu.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        recordingMenu.menu.addAction('Custom Duration…', () => this._customRecording());
        this.menu.addMenuItem(recordingMenu);
        this._recordingMenu = recordingMenu;

        this._stopItem = new PopupMenu.PopupMenuItem('Stop Recording');
        this._stopItem.connect('activate', () => this._stopRecording());
        this._stopItem.visible = false;
        this.menu.addMenuItem(this._stopItem);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this.menu.addAction('Preferences', () => this._launch('--preferences'));
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
        if (this._captureInProgress || this._recordingPath !== null)
            return;

        this._captureInProgress = true;
        this.menu.close();
        this._captureTimeoutId = GLib.timeout_add(
            GLib.PRIORITY_DEFAULT,
            CAPTURE_DELAY_MS,
            () => {
                this._captureTimeoutId = 0;
                if (this._destroying) {
                    this._captureInProgress = false;
                    return GLib.SOURCE_REMOVE;
                }
                this._takeScreenshot();
                return GLib.SOURCE_REMOVE;
            });
    }

    _takeScreenshot() {
        const captureDirectory = GLib.build_filenamev([
            GLib.get_user_runtime_dir(),
            'grab-captures',
        ]);
        const filename = `grab-${GLib.uuid_string_random()}.png`;
        const path = GLib.build_filenamev([
            captureDirectory,
            filename,
        ]);
        const file = Gio.File.new_for_path(path);
        let stream;

        try {
            if (GLib.mkdir_with_parents(captureDirectory, 0o700) !== 0)
                throw new Error('Could not prepare Grab\'s temporary capture directory.');
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
                        this._deleteRecording(path);
                } catch (error) {
                    try {
                        stream.close(null);
                    } catch (_closeError) {
                        // The original capture error is more useful.
                    }
                    this._deleteRecording(path);
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

    _customRecording() {
        if (this._recordingPath !== null)
            return;
        this._durationDialog?.close();
        this._durationDialog = new DurationDialog(this._customDuration, duration => {
            this._customDuration = duration;
            this._durationDialog = null;
            this._startRecording(duration);
        });
        this._durationDialog.connect('closed', () => {
            this._durationDialog = null;
        });
        this._durationDialog.open();
    }

    _startRecording(duration) {
        if (this._recordingPath !== null || this._captureInProgress)
            return;
        const pathStem = GLib.build_filenamev([
            GLib.get_user_runtime_dir(),
            `grab-recording-${GLib.uuid_string_random()}`,
        ]);
        this._recordingPath = pathStem;
        this._recordingDuration = duration;
        const options = {
            'draw-cursor': new GLib.Variant('b', true),
            'framerate': new GLib.Variant('i', 15),
        };
        this._getScreencast((proxy, error) => {
            if (this._destroying) {
                this._deleteRecording(pathStem);
                return;
            }
            if (error !== null) {
                this._deleteRecording(pathStem);
                this._resetRecording();
                Main.notify(
                    'Grab could not start recording',
                    error instanceof Error ? error.message : String(error));
                return;
            }
            proxy.call(
                'Screencast',
                new GLib.Variant('(sa{sv})', [pathStem, options]),
                Gio.DBusCallFlags.NONE,
                -1,
                this._cancellable,
                (proxy, result) => {
                    if (this._destroying) {
                        this._deleteRecording(pathStem);
                        return;
                    }
                    let recordingPath = pathStem;
                    try {
                        const [success, filename] = proxy.call_finish(result).deepUnpack();
                        const supportedPaths = [
                            `${pathStem}.mp4`,
                            `${pathStem}.webm`,
                        ];
                        if (!success || !supportedPaths.includes(filename))
                            throw new Error('GNOME Shell could not start the recording.');
                        recordingPath = filename;
                        this._recordingPath = recordingPath;
                        this._recordingStarted(duration);
                    } catch (error) {
                        this._stopFailedRecording(proxy, recordingPath, error);
                    }
                });
        });
    }

    _stopFailedRecording(proxy, path, error) {
        proxy.call(
            'StopScreencast',
            null,
            Gio.DBusCallFlags.NONE,
            -1,
            this._cancellable,
            (proxy, result) => {
                try {
                    proxy.call_finish(result);
                } catch (stopError) {
                    if (!this._destroying)
                        console.warn(`Grab could not stop recording: ${stopError.message}`);
                }
                this._deleteRecording(path);
                this._resetRecording();
                if (!this._destroying) {
                    Main.notify(
                        'Grab could not start recording',
                        error instanceof Error ? error.message : String(error));
                }
            });
    }

    _getScreencast(callback) {
        if (this._screencast !== null) {
            callback(this._screencast, null);
            return;
        }
        Gio.DBusProxy.new_for_bus(
            Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE,
            null,
            SCREENCAST_BUS,
            SCREENCAST_PATH,
            SCREENCAST_INTERFACE,
            this._cancellable,
            (_source, result) => {
                try {
                    this._screencast = Gio.DBusProxy.new_for_bus_finish(result);
                    this._errorSignal = this._screencast.connectSignal(
                        'Error', (_proxy, _sender, [name, message]) => {
                            if (this._recordingPath === null)
                                return;
                            Main.notify('Grab recording failed', message || name);
                            this._deleteRecording(this._recordingPath);
                            this._resetRecording();
                        });
                    callback(this._screencast, null);
                } catch (error) {
                    callback(null, error);
                }
            });
    }

    _recordingStarted(duration) {
        this._remaining = duration;
        this._icon.icon_name = 'media-record-symbolic';
        this._recordingMenu.sensitive = false;
        this._stopItem.visible = true;
        this._updateStopLabel();
        this._timerId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
            this._remaining -= 1;
            this._updateStopLabel();
            if (this._remaining <= 0) {
                this._timerId = 0;
                this._stopRecording();
                return GLib.SOURCE_REMOVE;
            }
            return GLib.SOURCE_CONTINUE;
        });
    }

    _updateStopLabel() {
        const suffix = this._remaining === 1 ? 'second' : 'seconds';
        this._stopItem.label.text = `Stop Recording (${this._remaining} ${suffix} remaining)`;
    }

    _stopRecording() {
        if (this._recordingPath === null || this._stopping)
            return;
        this._stopping = true;
        if (this._timerId) {
            GLib.source_remove(this._timerId);
            this._timerId = 0;
        }
        const path = this._recordingPath;
        this._screencast.call(
            'StopScreencast',
            null,
            Gio.DBusCallFlags.NONE,
            -1,
            this._cancellable,
            (proxy, result) => {
                if (this._destroying) {
                    this._deleteRecording(path);
                    return;
                }
                try {
                    const [success] = proxy.call_finish(result).deepUnpack();
                    if (!success)
                        throw new Error('GNOME Shell could not stop the recording cleanly.');
                    this._resetRecording();
                    if (!Gio.File.new_for_path(path).query_exists(null))
                        throw new Error('GNOME Shell did not produce a recording file.');
                    if (!this._launch('--recording-file', path))
                        this._deleteRecording(path);
                } catch (error) {
                    this._deleteRecording(path);
                    this._resetRecording();
                    Main.notify(
                        'Grab could not finish recording',
                        error instanceof Error ? error.message : String(error));
                }
            });
    }

    _resetRecording() {
        if (this._timerId) {
            GLib.source_remove(this._timerId);
            this._timerId = 0;
        }
        this._recordingPath = null;
        this._recordingDuration = 0;
        this._remaining = 0;
        this._stopping = false;
        this._icon.icon_name = 'camera-photo-symbolic';
        this._recordingMenu.sensitive = true;
        this._stopItem.visible = false;
        this._stopItem.label.text = 'Stop Recording';
    }

    _deleteRecording(path) {
        const file = Gio.File.new_for_path(path);
        file.delete_async(GLib.PRIORITY_DEFAULT, null, (_file, result) => {
            try {
                file.delete_finish(result);
            } catch (error) {
                if (!error.matches(Gio.IOErrorEnum, Gio.IOErrorEnum.NOT_FOUND))
                    console.warn(`Grab could not remove ${path}: ${error.message}`);
            }
        });
    }

    destroy() {
        this._destroying = true;
        if (this._captureTimeoutId) {
            GLib.source_remove(this._captureTimeoutId);
            this._captureTimeoutId = 0;
            this._captureInProgress = false;
        }
        this._durationDialog?.close();
        this._durationDialog = null;
        if (this._recordingPath !== null && this._screencast !== null) {
            const path = this._recordingPath;
            try {
                this._screencast.call_sync(
                    'StopScreencast',
                    null,
                    Gio.DBusCallFlags.NONE,
                    -1,
                    null);
            } catch (error) {
                console.warn(`Grab could not stop recording: ${error.message}`);
            }
            this._deleteRecording(path);
        }
        this._resetRecording();
        if (this._errorSignal && this._screencast !== null) {
            this._screencast.disconnectSignal(this._errorSignal);
            this._errorSignal = 0;
        }
        this._cancellable.cancel();
        super.destroy();
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
