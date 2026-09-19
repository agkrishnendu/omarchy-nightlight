import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// Bar pill + popup for the bundled nightlight-schedule script. All schedule
// and override logic lives in that script; this only renders its `--json`
// status, runs its `sync` on a poll, and calls its set/resume/restart
// commands.
Panel {
  id: root
  moduleName: "krisag.nightlight"
  ipcTarget: "krisag.nightlight"
  manageIpc: false

  // Run through python3 so the plugin works even if git drops the exec bit.
  readonly property string script: decodeURIComponent(String(Qt.resolvedUrl("nightlight-schedule")).replace(/^file:\/\//, ""))
  readonly property var scheduleArgs: [
    "--evening-temp", String(setting("eveningTemperature", 3400)),
    "--late-temp", String(setting("lateTemperature", 2700)),
    "--late-after", String(setting("lateAfterMinutes", 180)),
    "--off-time", /^([01]?\d|2[0-3]):[0-5]\d$/.test(String(setting("offTime", ""))) ? String(setting("offTime", "")) : "07:00"
  ]
  readonly property string moonIcon: String.fromCodePoint(0xF0594)
  readonly property string sunIcon: String.fromCodePoint(0xF0599)
  readonly property string alertIcon: String.fromCodePoint(0xF0026)

  property var status: null
  // Hold applied by the preset/slider buttons; follows an active override.
  property string hold: "next"
  readonly property var holds: [
    { value: "next", label: "Next change" },
    { value: "1h", label: "1 hour" },
    { value: "morning", label: "Morning" }
  ]

  readonly property var override: status ? status.override : null
  readonly property bool healthy: status ? status.ok === true : true
  readonly property var effective: status ? status.effective : null
  // Shown in the evening, while overridden, when broken at night, or when
  // opened by IPC during the day.
  readonly property bool shown: opened || (status !== null && (status.night === true || override !== null))

  function kelvin(k) { return k === null || k === undefined ? "Off" : k + "K" }

  function heroStatusText() {
    if (!status) return "Loading"
    if (status.problem && status.profiles.length === 0) return "No schedule"
    if (!status.running) return "Not running"
    if (!healthy) return "Not responding"
    if (override) return "Override · until " + override.untilLabel
    if (status.next) return "Schedule · " + kelvin(status.next.temperature) + " at " + status.next.time
    return "Schedule"
  }

  function tooltip() {
    if (!status) return ""
    if (!healthy) return "Night light: hyprsunset not responding"
    var text = "Night light " + kelvin(effective)
    if (override) return text + " (override until " + override.untilLabel + ")"
    if (status.next) text += " · " + kelvin(status.next.temperature) + " at " + status.next.time
    return text
  }

  function run(args) {
    if (actionProc.running) return
    actionProc.command = ["python3", root.script].concat(args).concat(["--json"])
    actionProc.running = true
  }

  function refresh() {
    if (!syncProc.running && !actionProc.running) syncProc.running = true
  }

  function setTemperature(value) { run(["set", String(value), "--until", root.hold]) }
  function resume() { run(["resume"]) }
  function restartHyprsunset() { run(["restart"]) }

  function setHold(value) {
    root.hold = value
    if (override) setTemperature(override.temperature === null ? "off" : override.temperature)
  }

  function quickToggle() {
    if (override) resume()
    else run(["set", "off", "--until", "next"])
  }

  function applyStatus(text) {
    try {
      root.status = JSON.parse(text)
    } catch (e) {
      return
    }
    if (root.override) root.hold = root.override.hold
    scheduleBoundary()
  }

  // Sync right after the next profile switch or override expiry, so an
  // override is restored without waiting for the poll.
  function scheduleBoundary() {
    var targets = []
    if (status && status.next) targets.push(status.next.epoch)
    if (override) targets.push(override.until)
    if (targets.length === 0) return
    var ms = Math.min.apply(null, targets) * 1000 - Date.now() + 1500
    if (ms > 0 && ms < 3600 * 1000) {
      boundaryTimer.interval = ms
      boundaryTimer.restart()
    }
  }

  IpcHandler {
    target: "krisag.nightlight"

    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): void { root.refresh() }
    function resume(): void { root.resume() }
  }

  onOpenedChanged: if (opened) refresh()
  onScheduleArgsChanged: refresh()
  Component.onCompleted: refresh()

  visible: shown
  implicitWidth: shown ? button.implicitWidth : 0
  implicitHeight: shown ? button.implicitHeight : 0

  Process {
    id: syncProc
    command: ["python3", root.script, "sync", "--json"].concat(root.scheduleArgs)
    stdout: StdioCollector { waitForEnd: true; onStreamFinished: root.applyStatus(text) }
  }

  Process {
    id: actionProc
    stdout: StdioCollector { waitForEnd: true; onStreamFinished: root.applyStatus(text) }
  }

  Timer { interval: 30000; running: true; repeat: true; onTriggered: root.refresh() }
  Timer { id: boundaryTimer; repeat: false; onTriggered: root.refresh() }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: !root.healthy ? root.alertIcon
      : (root.override && root.override.temperature === null ? root.sunIcon : root.moonIcon)
    active: root.override !== null || !root.healthy
    tooltipText: root.opened ? "" : root.tooltip()
    onPressed: function(b) {
      if (b === Qt.RightButton) root.quickToggle()
      else if (b === Qt.MiddleButton) root.refresh()
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(360))
    contentHeight: panel.fittedContentHeight(column.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Column {
        id: column
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: Style.space(14)

        // ---------- Hero: icon · title/status · current temperature ----------
        Item {
          width: parent.width
          implicitHeight: Math.max(heroIcon.implicitHeight, heroLabels.implicitHeight, heroValue.implicitHeight)

          Text {
            id: heroIcon
            textFormat: Text.PlainText
            text: button.text
            color: root.bar.foreground
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.display
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
          }

          Column {
            id: heroLabels
            anchors.left: heroIcon.right
            anchors.leftMargin: Style.space(14)
            anchors.right: heroValue.left
            anchors.rightMargin: Style.space(10)
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(2)

            Text {
              text: "Night Light"
              color: root.bar.foreground
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.title
              font.bold: true
              elide: Text.ElideRight
              width: parent.width
            }

            Text {
              textFormat: Text.PlainText
              text: root.heroStatusText().toUpperCase()
              color: Qt.darker(root.bar.foreground, 1.4)
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
              font.letterSpacing: 1.2
              elide: Text.ElideRight
              width: parent.width
            }
          }

          Text {
            id: heroValue
            textFormat: Text.PlainText
            text: root.status ? root.kelvin(root.effective) : "—"
            color: root.bar.foreground
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.displayLarge
            font.bold: true
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
          }
        }

        InfoLabel {
          visible: root.status !== null && !!root.status.problem
          width: parent.width
          wrapMode: Text.WordWrap
          text: root.status && root.status.problem ? "Couldn't update the schedule: " + root.status.problem : ""
        }

        // ---------- hyprsunset unreachable ----------
        Row {
          visible: root.status !== null && !root.healthy
          width: parent.width
          spacing: Style.space(10)

          InfoLabel {
            width: parent.width - restartButton.width - parent.spacing
            anchors.verticalCenter: parent.verticalCenter
            wrapMode: Text.WordWrap
            text: root.status && root.status.running
              ? "hyprsunset is running but not answering, so the schedule can't be changed."
              : "hyprsunset is not running."
          }

          Button {
            id: restartButton
            text: root.status && root.status.running ? "Restart" : "Start"
            fontSize: Style.font.bodySmall
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            bordered: true
            onClicked: root.restartHyprsunset()
          }
        }

        // ---------- Today's schedule ----------
        PanelSeparator { foreground: root.bar.foreground }

        Column {
          width: parent.width
          spacing: Style.spacing.labelGap

          PanelSectionHeader {
            text: "SCHEDULE"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
          }

          Repeater {
            model: root.status ? root.status.profiles : []

            Row {
              required property var modelData
              readonly property bool current: root.status.scheduled !== null && root.status.scheduled.time === modelData.time && !root.override

              width: parent.width
              spacing: Style.space(8)
              opacity: current ? 1 : 0.6

              InfoValue {
                text: (parent.current ? "● " : "  ") + parent.modelData.time
                font.bold: parent.current
              }
              Item { width: Math.max(0, parent.width - parent.children[0].implicitWidth - parent.children[2].implicitWidth - parent.spacing * 2); height: 1 }
              InfoValue {
                text: root.kelvin(parent.modelData.temperature)
                font.bold: parent.current
              }
            }
          }
        }

        // ---------- Override ----------
        PanelSeparator { foreground: root.bar.foreground }

        Column {
          width: parent.width
          spacing: Style.space(10)

          PanelSectionHeader {
            text: "OVERRIDE"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
          }

          Row {
            id: presetRow
            width: parent.width
            spacing: Style.space(6)

            readonly property var presets: ["off"].concat(root.status ? root.status.presets : [])
            readonly property real cellWidth: (width - spacing * (presets.length - 1)) / presets.length

            Repeater {
              model: presetRow.presets

              Button {
                required property var modelData
                width: presetRow.cellWidth
                text: modelData === "off" ? "Off" : modelData + "K"
                fontSize: Style.font.bodySmall
                foreground: root.bar.foreground
                fontFamily: root.bar.fontFamily
                bordered: true
                active: root.override !== null
                  && (modelData === "off" ? root.override.temperature === null : root.override.temperature === modelData)
                onClicked: root.setTemperature(modelData)
              }
            }
          }

          Row {
            width: parent.width
            spacing: Style.space(10)

            PanelSlider {
              id: slider
              bar: root.bar
              width: parent.width - sliderValue.width - parent.spacing
              anchors.verticalCenter: parent.verticalCenter
              minimum: 1900
              maximum: 6500
              step: 100
              integer: true
              value: typeof root.effective === "number" ? root.effective : 6500
              onReleased: function(v) { root.setTemperature(Math.round(v)) }
            }

            InfoValue {
              id: sliderValue
              width: Style.space(52)
              horizontalAlignment: Text.AlignRight
              anchors.verticalCenter: parent.verticalCenter
              text: Math.round(slider.liveValue) + "K"
            }
          }

          Row {
            id: holdRow
            width: parent.width
            spacing: Style.space(6)

            readonly property real cellWidth: (width - spacing * (root.holds.length - 1)) / root.holds.length

            Repeater {
              model: root.holds

              Button {
                required property var modelData
                width: holdRow.cellWidth
                text: modelData.label
                fontSize: Style.font.bodySmall
                foreground: root.bar.foreground
                fontFamily: root.bar.fontFamily
                bordered: true
                active: root.hold === modelData.value
                onClicked: root.setHold(modelData.value)
              }
            }
          }

          Button {
            visible: root.override !== null
            width: parent.width
            text: "Resume schedule"
            fontSize: Style.font.bodySmall
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            bordered: true
            onClicked: root.resume()
          }
        }
      }
    }
  }

  component InfoLabel: Text {
    textFormat: Text.PlainText
    color: root.bar.foreground
    opacity: 0.6
    font.family: root.bar.fontFamily
    font.pixelSize: Style.font.bodySmall
  }

  component InfoValue: Text {
    textFormat: Text.PlainText
    color: root.bar.foreground
    font.family: root.bar.fontFamily
    font.pixelSize: Style.font.bodySmall
  }
}
