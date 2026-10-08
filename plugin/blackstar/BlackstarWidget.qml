import QtQuick
import qs.Common
import qs.Services
import qs.Widgets
import qs.Modules.Plugins

PluginComponent {
    id: root

    property bool connected: false
    property string model: "ID:Core"
    property int slot: 0
    property var names: []
    property string voice: ""
    property var settings: ({})
    property bool busy: false

    readonly property string patchName: slot > 0 && names.length >= slot ? names[slot - 1] : ""

    function cmd(args) {
        return ["sh", "-c", "exec \"$HOME/.local/bin/bsamp\" " + args];
    }

    function refresh() {
        Proc.runCommand("bsamp.status", cmd("status --json"), (out, code) => {
            let s;
            try {
                s = JSON.parse(out);
            } catch (e) {
                root.connected = false;
                return;
            }
            root.connected = s.connected;
            if (!s.connected)
                return;
            root.model = s.model;
            root.slot = s.slot || 0;
            root.names = s.names;
            root.voice = s.voice;
            root.settings = s.settings;
        }, 50, 8000, root);
    }

    function run(args) {
        busy = true;
        Proc.runCommand(null, cmd(args), (out, code) => {
            busy = false;
            if (code !== 0)
                ToastService.showError("Amp", "bsamp " + args + " failed");
            root.refresh();
        }, 0, 15000, root);
    }

    function openApp() {
        Proc.runCommand(null, ["sh", "-c", "setsid -f \"$HOME/.local/bin/bsamp\" gui >/dev/null 2>&1"], () => {}, 0);
    }

    // Slow poll in the background, fast while the popout is open.
    Timer {
        interval: root.popoutOpen ? 3000 : 15000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.refresh()
    }

    property bool popoutOpen: false

    Timer {
        id: knobDebounce

        property string control: ""
        property int value: 0

        interval: 120
        onTriggered: root.run("set " + control + " " + value)
    }

    pillRightClickAction: () => root.openApp()

    popoutWidth: 380
    popoutHeight: 470

    horizontalBarPill: Component {
        Row {
            spacing: Theme.spacingXS

            DankIcon {
                name: "speaker"
                color: root.connected ? Theme.primary : Theme.surfaceVariantText
                size: root.iconSize
                anchors.verticalCenter: parent.verticalCenter
            }

            StyledText {
                visible: root.connected
                text: root.patchName !== "" ? root.patchName : root.voice
                color: Theme.surfaceText
                font.pixelSize: root.textSize
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    verticalBarPill: Component {
        Column {
            spacing: Theme.spacingXS

            DankIcon {
                name: "speaker"
                color: root.connected ? Theme.primary : Theme.surfaceVariantText
                size: root.iconSize
                anchors.horizontalCenter: parent.horizontalCenter
            }

            StyledText {
                visible: root.connected && root.slot > 0
                text: root.slot
                color: Theme.surfaceText
                font.pixelSize: Theme.fontSizeSmall
                anchors.horizontalCenter: parent.horizontalCenter
            }
        }
    }

    popoutContent: Component {
        PopoutComponent {
            headerText: root.model
            detailsText: !root.connected ? "Not connected - plug in the amp and switch it on" : (root.slot > 0 ? ("Slot " + root.slot + " · " + root.voice) : root.voice)
            showCloseButton: true

            Component.onCompleted: {
                root.popoutOpen = true;
                root.refresh();
            }
            Component.onDestruction: root.popoutOpen = false

            Column {
                width: parent.width
                spacing: Theme.spacingS

                // --- Patches: 2 x 3 grid ---
                Grid {
                    width: parent.width
                    columns: 2
                    spacing: Theme.spacingXS
                    visible: root.connected

                    Repeater {
                        model: 6

                        Rectangle {
                            required property int index
                            readonly property bool active: root.slot === index + 1

                            width: (parent.width - Theme.spacingXS) / 2
                            height: 46
                            radius: Theme.cornerRadius
                            color: active ? Theme.primary : (slotArea.containsMouse ? Theme.surfaceContainerHighest : Theme.surfaceContainerHigh)

                            Row {
                                anchors.fill: parent
                                anchors.leftMargin: Theme.spacingS
                                anchors.rightMargin: Theme.spacingS
                                spacing: Theme.spacingS

                                StyledText {
                                    text: index + 1
                                    font.pixelSize: Theme.fontSizeLarge
                                    font.weight: Font.Bold
                                    color: active ? Theme.primaryText : Theme.primary
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                StyledText {
                                    width: parent.width - 30
                                    text: root.names[index] || "Empty"
                                    elide: Text.ElideRight
                                    font.pixelSize: Theme.fontSizeSmall
                                    color: active ? Theme.primaryText : Theme.surfaceText
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                            }

                            MouseArea {
                                id: slotArea

                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                enabled: !root.busy
                                onClicked: {
                                    root.slot = index + 1;
                                    root.run("select " + (index + 1));
                                }
                            }
                        }
                    }
                }

                // --- Effects on/off ---
                Repeater {
                    model: [{
                        "key": "mod",
                        "label": "Modulation",
                        "icon": "waves"
                    }, {
                        "key": "delay",
                        "label": "Delay",
                        "icon": "repeat"
                    }, {
                        "key": "reverb",
                        "label": "Reverb",
                        "icon": "blur_on"
                    }]

                    Item {
                        required property var modelData

                        visible: root.connected
                        width: parent.width
                        height: fxToggle.height

                        Row {
                            anchors.left: parent.left
                            anchors.leftMargin: Theme.spacingS
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: Theme.spacingS

                            DankIcon {
                                name: modelData.icon
                                size: Theme.iconSize
                                color: root.settings[modelData.key] ? Theme.primary : Theme.surfaceText
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            StyledText {
                                text: modelData.label
                                font.pixelSize: Theme.fontSizeMedium
                                color: Theme.surfaceText
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }

                        DankToggle {
                            id: fxToggle

                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            hideText: true
                            checked: !!root.settings[modelData.key]
                            onToggled: checked => root.run("set " + modelData.key + " " + (checked ? "on" : "off"))
                        }
                    }
                }

                // --- Gain / Volume ---
                Repeater {
                    model: [{
                        "key": "gain",
                        "label": "Gain"
                    }, {
                        "key": "volume",
                        "label": "Volume"
                    }]

                    Column {
                        required property var modelData

                        visible: root.connected
                        width: parent.width

                        StyledText {
                            leftPadding: Theme.spacingS
                            text: modelData.label + "  " + ((root.settings[modelData.key] || 0) / 12.7).toFixed(1)
                            font.pixelSize: Theme.fontSizeSmall
                            color: Theme.surfaceVariantText
                        }

                        DankSlider {
                            width: parent.width
                            minimum: 0
                            maximum: 127
                            value: root.settings[modelData.key] || 0
                            onSliderValueChanged: newValue => {
                                knobDebounce.control = modelData.key;
                                knobDebounce.value = newValue;
                                knobDebounce.restart();
                            }
                        }
                    }
                }

                Row {
                    spacing: Theme.spacingS
                    anchors.horizontalCenter: parent.horizontalCenter

                    DankButton {
                        text: "Open app"
                        iconName: "tune"
                        onClicked: root.openApp()
                    }

                    DankButton {
                        visible: !root.connected
                        text: "Retry"
                        iconName: "refresh"
                        onClicked: root.refresh()
                    }
                }
            }
        }
    }
}
