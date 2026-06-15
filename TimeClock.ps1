# RuffLife-TimeClock.ps1 — v2

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$LOG_FILE   = Join-Path $SCRIPT_DIR "timelog.csv"

$NAVY  = [System.Drawing.Color]::FromArgb( 27,  42,  74)
$NAVY2 = [System.Drawing.Color]::FromArgb( 20,  32,  58)
$NAVY3 = [System.Drawing.Color]::FromArgb( 36,  53,  90)
$MAUVE = [System.Drawing.Color]::FromArgb(176, 122, 142)
$GOLD  = [System.Drawing.Color]::FromArgb(255, 193,   7)
$GREEN = [System.Drawing.Color]::FromArgb( 25, 135,  84)
$RED   = [System.Drawing.Color]::FromArgb(220,  53,  69)
$WHITE = [System.Drawing.Color]::White
$MUTED = [System.Drawing.Color]::FromArgb(107, 114, 128)

$CATEGORIES = @('Bug Fix','Feature Development','Database / Migration',
                'Security','Deployment','Testing / QA',
                'Documentation / KB','General Support','Meeting / Discussion')

$script:Running    = $false
$script:StartTime  = $null
$script:SessionSec = 0
$script:Sessions   = [System.Collections.Generic.List[PSObject]]::new()
$script:CalYear    = (Get-Date).Year
$script:CalMonth   = (Get-Date).Month

function Format-Dur($secs) {
    $secs = [math]::Max(0, $secs)
    $h = [math]::Floor($secs / 3600)
    $m = [math]::Floor(($secs % 3600) / 60)
    $s = [math]::Floor($secs % 60)
    return ($h.ToString().PadLeft(2,'0') + ':' + $m.ToString().PadLeft(2,'0') + ':' + $s.ToString().PadLeft(2,'0'))
}

function Get-TodaySec {
    $t = (Get-Date).ToString('yyyy-MM-dd')
    $sum = ($script:Sessions | Where-Object {$_.Date -eq $t} | Measure-Object -Property Seconds -Sum).Sum
    if ($sum) { return [double]$sum } else { return 0 }
}

function Load-Log {
    if (Test-Path $LOG_FILE) { Import-Csv $LOG_FILE | ForEach-Object { $script:Sessions.Add($_) } }
}

function Save-Session($cat,$desc,$start,$end,$secs) {
    $row = [PSCustomObject]@{
        Date=$start.ToString('yyyy-MM-dd'); Start=$start.ToString('HH:mm:ss')
        End=$end.ToString('HH:mm:ss'); Category=$cat; Description=$desc
        Seconds=[math]::Round($secs); Hours=[math]::Round($secs/3600,4)
    }
    $script:Sessions.Add($row)
    $row | Export-Csv -Path $LOG_FILE -Append -NoTypeInformation
    return $row
}

# ── Form ──────────────────────────────────────────────────────────────────────
$form = New-Object System.Windows.Forms.Form
$form.Text = 'Ruff Life Retreat — Time Clock'
$form.Size = New-Object System.Drawing.Size(560, 760)
$form.MinimumSize = New-Object System.Drawing.Size(560, 680)
$form.StartPosition = 'CenterScreen'
$form.BackColor = $NAVY; $form.ForeColor = $WHITE
$form.FormBorderStyle = 'Sizable'; $form.MaximizeBox = $true
$form.KeyPreview = $true
$form.Font = New-Object System.Drawing.Font('Segoe UI', 9)

# Header
$pnlHead = New-Object System.Windows.Forms.Panel
$pnlHead.Dock = 'Top'; $pnlHead.Height = 68; $pnlHead.BackColor = $NAVY2

$lT = New-Object System.Windows.Forms.Label
$lT.Text = '🐾  RUFF LIFE RETREAT'
$lT.Font = New-Object System.Drawing.Font('Segoe UI', 12, [System.Drawing.FontStyle]::Bold)
$lT.ForeColor = $GOLD; $lT.Location = New-Object System.Drawing.Point(14,6)
$lT.Size = New-Object System.Drawing.Size(530,26)

$lS = New-Object System.Windows.Forms.Label
$lS.Text = 'Support Time Tracker'; $lS.Font = New-Object System.Drawing.Font('Segoe UI',8)
$lS.ForeColor = $MAUVE; $lS.Location = New-Object System.Drawing.Point(14,34); $lS.Size = New-Object System.Drawing.Size(250,16)

$lD = New-Object System.Windows.Forms.Label
$lD.Text = (Get-Date).ToString('dddd, MMMM d')
$lD.Font = New-Object System.Drawing.Font('Segoe UI',8); $lD.ForeColor = $MUTED
$lD.Location = New-Object System.Drawing.Point(14,50); $lD.Size = New-Object System.Drawing.Size(300,16)

$pnlHead.Controls.AddRange(@($lT,$lS,$lD)); $form.Controls.Add($pnlHead)

# Tabs
$tabs = New-Object System.Windows.Forms.TabControl
$tabs.Location = New-Object System.Drawing.Point(0,68)
$tabs.Size = New-Object System.Drawing.Size(554,666)
$tabs.DrawMode = 'OwnerDrawFixed'
$tabs.ItemSize = New-Object System.Drawing.Size(276,30)
$tabs.SizeMode = 'Fixed'
$tabs.BackColor = $NAVY
$tabs.Anchor = [System.Windows.Forms.AnchorStyles]::Top -bor [System.Windows.Forms.AnchorStyles]::Bottom -bor [System.Windows.Forms.AnchorStyles]::Left -bor [System.Windows.Forms.AnchorStyles]::Right

$tabs.Add_DrawItem({
    param($s,$e)
    $tab = $s.TabPages[$e.Index]
    if ($e.Index -eq $s.SelectedIndex) { $bg = $NAVY3; $fg = $GOLD } else { $bg = $NAVY2; $fg = $MUTED }
    $e.Graphics.FillRectangle((New-Object System.Drawing.SolidBrush($bg)), $e.Bounds)
    $sf = New-Object System.Drawing.StringFormat
    $sf.Alignment = 'Center'; $sf.LineAlignment = 'Center'
    $rect = [System.Drawing.RectangleF]::new($e.Bounds.X, $e.Bounds.Y, $e.Bounds.Width, $e.Bounds.Height)
    $e.Graphics.DrawString($tab.Text, $e.Font, (New-Object System.Drawing.SolidBrush($fg)), $rect, $sf)
})

$tabTimer    = New-Object System.Windows.Forms.TabPage; $tabTimer.Text = '  Timer  '; $tabTimer.BackColor = $NAVY
$tabCalendar = New-Object System.Windows.Forms.TabPage; $tabCalendar.Text = '  Calendar  '; $tabCalendar.BackColor = $NAVY
$tabs.TabPages.AddRange(@($tabTimer,$tabCalendar))
$form.Controls.Add($tabs)

# ── TIMER TAB ─────────────────────────────────────────────────────────────────
# Timer box
$pTB = New-Object System.Windows.Forms.Panel
$pTB.Location = New-Object System.Drawing.Point(12,12); $pTB.Size = New-Object System.Drawing.Size(518,108); $pTB.BackColor = $NAVY3

$lCC = New-Object System.Windows.Forms.Label; $lCC.Text = 'CURRENT SESSION'
$lCC.Font = New-Object System.Drawing.Font('Segoe UI',7,[System.Drawing.FontStyle]::Bold)
$lCC.ForeColor = $MAUVE; $lCC.Location = New-Object System.Drawing.Point(10,8); $lCC.Size = New-Object System.Drawing.Size(200,16)

$lTimer = New-Object System.Windows.Forms.Label; $lTimer.Text = '00:00:00'
$lTimer.Font = New-Object System.Drawing.Font('Consolas',40,[System.Drawing.FontStyle]::Bold)
$lTimer.ForeColor = $WHITE; $lTimer.Location = New-Object System.Drawing.Point(6,22); $lTimer.Size = New-Object System.Drawing.Size(300,66)

$lStatus = New-Object System.Windows.Forms.Label; $lStatus.Text = '⏸  Stopped'
$lStatus.Font = New-Object System.Drawing.Font('Segoe UI',9); $lStatus.ForeColor = $MUTED
$lStatus.Location = New-Object System.Drawing.Point(10,88); $lStatus.Size = New-Object System.Drawing.Size(250,16)

$lCT = New-Object System.Windows.Forms.Label; $lCT.Text = 'TODAY TOTAL'
$lCT.Font = New-Object System.Drawing.Font('Segoe UI',7,[System.Drawing.FontStyle]::Bold)
$lCT.ForeColor = $MAUVE; $lCT.Location = New-Object System.Drawing.Point(318,8); $lCT.Size = New-Object System.Drawing.Size(196,16)

$lTotal = New-Object System.Windows.Forms.Label; $lTotal.Text = '00:00:00'
$lTotal.Font = New-Object System.Drawing.Font('Consolas',22,[System.Drawing.FontStyle]::Bold)
$lTotal.ForeColor = $GOLD; $lTotal.Location = New-Object System.Drawing.Point(316,24); $lTotal.Size = New-Object System.Drawing.Size(198,36)

$lSCount = New-Object System.Windows.Forms.Label; $lSCount.Text = '0 sessions today'
$lSCount.Font = New-Object System.Drawing.Font('Segoe UI',8); $lSCount.ForeColor = $MUTED
$lSCount.Location = New-Object System.Drawing.Point(318,64); $lSCount.Size = New-Object System.Drawing.Size(196,16)

$pTB.Controls.AddRange(@($lCC,$lTimer,$lStatus,$lCT,$lTotal,$lSCount))
$tabTimer.Controls.Add($pTB)

function Add-Label($text,$x,$y,$tab) {
    $l = New-Object System.Windows.Forms.Label; $l.Text = $text
    $l.Font = New-Object System.Drawing.Font('Segoe UI',7,[System.Drawing.FontStyle]::Bold)
    $l.ForeColor = $MAUVE; $l.Location = New-Object System.Drawing.Point($x,$y); $l.Size = New-Object System.Drawing.Size(400,16)
    $tab.Controls.Add($l)
}

Add-Label 'CATEGORY' 12 132 $tabTimer
$cmbCat = New-Object System.Windows.Forms.ComboBox
$cmbCat.Location = New-Object System.Drawing.Point(12,150); $cmbCat.Size = New-Object System.Drawing.Size(518,28)
$cmbCat.DropDownStyle = 'DropDownList'; $cmbCat.BackColor = $NAVY3; $cmbCat.ForeColor = $WHITE; $cmbCat.FlatStyle = 'Flat'
$CATEGORIES | ForEach-Object { [void]$cmbCat.Items.Add($_) }; $cmbCat.SelectedIndex = 0
$tabTimer.Controls.Add($cmbCat)

Add-Label 'DESCRIPTION  (what are you working on?)' 12 186 $tabTimer
$txtDesc = New-Object System.Windows.Forms.TextBox
$txtDesc.Location = New-Object System.Drawing.Point(12,204); $txtDesc.Size = New-Object System.Drawing.Size(518,60)
$txtDesc.Multiline = $true; $txtDesc.BackColor = $NAVY3; $txtDesc.ForeColor = $WHITE
$txtDesc.BorderStyle = 'None'; $txtDesc.Font = New-Object System.Drawing.Font('Segoe UI',9)
$tabTimer.Controls.Add($txtDesc)

function New-Btn2($text,$x,$y,$w,$h,$bg,$fg) {
    $b = New-Object System.Windows.Forms.Button; $b.Text = $text
    $b.Location = New-Object System.Drawing.Point($x,$y); $b.Size = New-Object System.Drawing.Size($w,$h)
    $b.BackColor = $bg; $b.ForeColor = $fg; $b.FlatStyle = 'Flat'; $b.FlatAppearance.BorderSize = 0
    $b.Font = New-Object System.Drawing.Font('Segoe UI',10,[System.Drawing.FontStyle]::Bold); $b.Cursor = 'Hand'
    return $b
}

$btnStart  = New-Btn2 '▶  START'   12  278  168  44  $GREEN $WHITE
$btnStop   = New-Btn2 '⏹  STOP'  188  278  168  44  $RED   $WHITE
$btnExport = New-Btn2 '📄  EXPORT' 364  278  166  44  $NAVY3 $GOLD
$btnManual = New-Btn2 '✏  MANUAL ENTRY' 12 328 518 38 $NAVY3 $MAUVE
$btnStop.Enabled = $false
$tabTimer.Controls.AddRange(@($btnStart,$btnStop,$btnExport,$btnManual))

Add-Label 'SESSION LOG — TODAY' 12 378 $tabTimer
$lvLog = New-Object System.Windows.Forms.ListView
$lvLog.Location = New-Object System.Drawing.Point(12,396); $lvLog.Size = New-Object System.Drawing.Size(518,248)
$lvLog.Anchor = [System.Windows.Forms.AnchorStyles]::Top -bor [System.Windows.Forms.AnchorStyles]::Bottom -bor [System.Windows.Forms.AnchorStyles]::Left -bor [System.Windows.Forms.AnchorStyles]::Right
$lvLog.View = 'Details'; $lvLog.BackColor = $NAVY3; $lvLog.ForeColor = $WHITE
$lvLog.BorderStyle = 'None'; $lvLog.FullRowSelect = $true
$lvLog.Font = New-Object System.Drawing.Font('Consolas',8)
foreach ($c in @(@{N='Start';W=65},@{N='End';W=65},@{N='Time';W=68},@{N='Category';W=140},@{N='Description';W=172})) {
    $ch = New-Object System.Windows.Forms.ColumnHeader; $ch.Text=$c.N; $ch.Width=$c.W; [void]$lvLog.Columns.Add($ch)
}
$tabTimer.Controls.Add($lvLog)

# ── CALENDAR TAB ──────────────────────────────────────────────────────────────
Add-Label 'MONTHLY WORK LOG' 12 10 $tabCalendar

$btnPrev = New-Btn2 '◀'  12  28  40  28  $NAVY3 $GOLD
$btnNext = New-Btn2 '▶' 500  28  40  28  $NAVY3 $GOLD
$lMon = New-Object System.Windows.Forms.Label
$lMon.Font = New-Object System.Drawing.Font('Segoe UI',11,[System.Drawing.FontStyle]::Bold)
$lMon.ForeColor = $WHITE; $lMon.TextAlign = 'MiddleCenter'
$lMon.Location = New-Object System.Drawing.Point(54,28); $lMon.Size = New-Object System.Drawing.Size(444,28)
$tabCalendar.Controls.AddRange(@($btnPrev,$lMon,$btnNext))

$DOW = @('Sun','Mon','Tue','Wed','Thu','Fri','Sat')
for ($i=0;$i -lt 7;$i++) {
    $lh = New-Object System.Windows.Forms.Label; $lh.Text = $DOW[$i]
    $lh.Font = New-Object System.Drawing.Font('Segoe UI',8,[System.Drawing.FontStyle]::Bold)
    $lh.ForeColor = $MAUVE; $lh.TextAlign = 'MiddleCenter'
    $lh.Location = New-Object System.Drawing.Point((12+$i*76),62); $lh.Size = New-Object System.Drawing.Size(74,18)
    $tabCalendar.Controls.Add($lh)
}

$script:DayCells = @()
for ($r=0;$r -lt 6;$r++) {
    for ($c=0;$c -lt 7;$c++) {
        $pnl = New-Object System.Windows.Forms.Panel
        $pnl.Size = New-Object System.Drawing.Size(74,64)
        $pnl.Location = New-Object System.Drawing.Point((12+$c*76),(82+$r*66))
        $pnl.BackColor = $NAVY3; $pnl.Cursor = 'Hand'

        $lN = New-Object System.Windows.Forms.Label
        $lN.Font = New-Object System.Drawing.Font('Segoe UI',9,[System.Drawing.FontStyle]::Bold)
        $lN.ForeColor = $WHITE; $lN.Location = New-Object System.Drawing.Point(4,3); $lN.Size = New-Object System.Drawing.Size(66,16)
        $lN.BackColor = [System.Drawing.Color]::Transparent

        $lH = New-Object System.Windows.Forms.Label
        $lH.Font = New-Object System.Drawing.Font('Consolas',8,[System.Drawing.FontStyle]::Bold)
        $lH.ForeColor = $GOLD; $lH.TextAlign = 'MiddleCenter'
        $lH.Location = New-Object System.Drawing.Point(2,22); $lH.Size = New-Object System.Drawing.Size(70,16)
        $lH.BackColor = [System.Drawing.Color]::Transparent

        $lC = New-Object System.Windows.Forms.Label
        $lC.Font = New-Object System.Drawing.Font('Segoe UI',7); $lC.ForeColor = $MUTED; $lC.TextAlign = 'MiddleCenter'
        $lC.Location = New-Object System.Drawing.Point(2,40); $lC.Size = New-Object System.Drawing.Size(70,16)
        $lC.BackColor = [System.Drawing.Color]::Transparent

        $pnl.Controls.AddRange(@($lN,$lH,$lC))
        $tabCalendar.Controls.Add($pnl)
        $script:DayCells += @{Panel=$pnl;Num=$lN;Hrs=$lH;Sess=$lC}
    }
}

# Day detail
$pDD = New-Object System.Windows.Forms.Panel
$pDD.Anchor = [System.Windows.Forms.AnchorStyles]::Bottom -bor [System.Windows.Forms.AnchorStyles]::Left -bor [System.Windows.Forms.AnchorStyles]::Right
$pDD.Location = New-Object System.Drawing.Point(12,480); $pDD.Size = New-Object System.Drawing.Size(518,140); $pDD.BackColor = $NAVY3
$lDDT = New-Object System.Windows.Forms.Label; $lDDT.Text = 'Click a day to view sessions'
$lDDT.Font = New-Object System.Drawing.Font('Segoe UI',8,[System.Drawing.FontStyle]::Bold)
$lDDT.ForeColor = $MAUVE; $lDDT.Location = New-Object System.Drawing.Point(8,6); $lDDT.Size = New-Object System.Drawing.Size(500,18)
$lvDD = New-Object System.Windows.Forms.ListView
$lvDD.Location = New-Object System.Drawing.Point(0,26); $lvDD.Size = New-Object System.Drawing.Size(518,114)
$lvDD.View = 'Details'; $lvDD.BackColor = $NAVY3; $lvDD.ForeColor = $WHITE; $lvDD.BorderStyle = 'None'
$lvDD.FullRowSelect = $true; $lvDD.Font = New-Object System.Drawing.Font('Consolas',8); $lvDD.HeaderStyle = 'None'
foreach ($c in @(@{N='Start';W=65},@{N='End';W=65},@{N='Time';W=68},@{N='Cat';W=140},@{N='Desc';W=172})) {
    $ch = New-Object System.Windows.Forms.ColumnHeader; $ch.Text=$c.N; $ch.Width=$c.W; [void]$lvDD.Columns.Add($ch)
}
$pDD.Controls.AddRange(@($lDDT,$lvDD)); $tabCalendar.Controls.Add($pDD)

function Render-Calendar {
    $y = $script:CalYear; $m = $script:CalMonth
    $lMon.Text = (Get-Date -Year $y -Month $m -Day 1).ToString('MMMM yyyy')
    $first = [int](Get-Date -Year $y -Month $m -Day 1).DayOfWeek
    $dim = [DateTime]::DaysInMonth($y,$m)
    $today = Get-Date
    $pad = $m.ToString().PadLeft(2,'0')

    $dayMap = @{}
    foreach ($s in $script:Sessions) {
        if ($s.Date -like "$y-$pad*") {
            if (-not $dayMap[$s.Date]) { $dayMap[$s.Date] = @{Secs=0;Count=0} }
            $dayMap[$s.Date].Secs  += [double]$s.Seconds
            $dayMap[$s.Date].Count++
        }
    }

    for ($i=0;$i -lt 42;$i++) {
        $cell = $script:DayCells[$i]; $dn = $i - $first + 1
        if ($dn -lt 1 -or $dn -gt $dim) {
            $cell.Panel.BackColor = $NAVY2; $cell.Num.Text=''; $cell.Hrs.Text=''; $cell.Sess.Text=''; $cell.Panel.Tag=$null
        } else {
            $ds = "$y-$pad-$($dn.ToString().PadLeft(2,'0'))"
            $isToday = ($y -eq $today.Year -and $m -eq $today.Month -and $dn -eq $today.Day)
            $cell.Num.Text = $dn.ToString(); $cell.Panel.Tag = $ds
            if ($dayMap[$ds]) {
                $cell.Panel.BackColor = [System.Drawing.Color]::FromArgb(25,80,55)
                $cell.Hrs.Text  = Format-Dur $dayMap[$ds].Secs
                $cnt = $dayMap[$ds].Count
                $cell.Sess.Text = "$cnt sess"
                $cell.Sess.ForeColor = $GOLD
                $cell.Num.ForeColor  = $WHITE
            } else {
                if ($isToday) { $cell.Panel.BackColor = [System.Drawing.Color]::FromArgb(40,60,110) } else { $cell.Panel.BackColor = $NAVY3 }
                if ($isToday) { $cell.Num.ForeColor = $GOLD } else { $cell.Num.ForeColor = $WHITE }
                $cell.Hrs.Text = ''; $cell.Sess.Text = ''
            }
            $clickDs = $ds
            $cell.Panel.Add_Click({ param($s,$e); Show-DayDetail $s.Tag }.GetNewClosure())
            foreach ($ctrl in $cell.Panel.Controls) {
                $ctrl.Add_Click({ param($s2,$e2); Show-DayDetail $s2.Parent.Tag }.GetNewClosure())
            }
        }
    }
}

function Show-DayDetail($ds) {
    if (-not $ds) { return }
    $d = [datetime]::ParseExact($ds,'yyyy-MM-dd',$null)
    $lDDT.Text = $d.ToString('dddd, MMMM d, yyyy')
    $lvDD.Items.Clear()
    $rows = $script:Sessions | Where-Object { $_.Date -eq $ds }
    if ($rows) {
        foreach ($s in $rows) {
            $it = New-Object System.Windows.Forms.ListViewItem($s.Start)
            [void]$it.SubItems.Add($s.End)
            [void]$it.SubItems.Add((Format-Dur ([double]$s.Seconds)))
            [void]$it.SubItems.Add($s.Category)
            [void]$it.SubItems.Add($s.Description)
            [void]$lvDD.Items.Add($it)
        }
    } else {
        $it = New-Object System.Windows.Forms.ListViewItem('No sessions on this day')
        $it.ForeColor = $MUTED; [void]$lvDD.Items.Add($it)
    }
}

$btnPrev.Add_Click({ $script:CalMonth--; if ($script:CalMonth -lt 1) {$script:CalMonth=12;$script:CalYear--}; Render-Calendar })
$btnNext.Add_Click({ $script:CalMonth++; if ($script:CalMonth -gt 12){$script:CalMonth=1;$script:CalYear++}; Render-Calendar })

# ── Refresh list ──────────────────────────────────────────────────────────────
function Refresh-ListView {
    $lvLog.Items.Clear()
    $t = (Get-Date).ToString('yyyy-MM-dd')
    foreach ($s in ($script:Sessions | Where-Object {$_.Date -eq $t})) {
        $it = New-Object System.Windows.Forms.ListViewItem($s.Start)
        [void]$it.SubItems.Add($s.End); [void]$it.SubItems.Add((Format-Dur ([double]$s.Seconds)))
        [void]$it.SubItems.Add($s.Category); [void]$it.SubItems.Add($s.Description); [void]$lvLog.Items.Add($it)
    }
    $cnt = ($script:Sessions | Where-Object {$_.Date -eq $t} | Measure-Object).Count
    $lSCount.Text = "$cnt session$(if($cnt -ne 1){'s'}) today"
    $lTotal.Text  = Format-Dur (Get-TodaySec)
}

# ── Ticker ────────────────────────────────────────────────────────────────────
$ticker = New-Object System.Windows.Forms.Timer; $ticker.Interval = 1000
$ticker.Add_Tick({
    if ($script:Running) {
        $script:SessionSec = ((Get-Date) - $script:StartTime).TotalSeconds
        $lTimer.Text = Format-Dur $script:SessionSec
        $lTotal.Text = Format-Dur ((Get-TodaySec) + $script:SessionSec)
    }
})
$ticker.Start()

# ── Button events ─────────────────────────────────────────────────────────────
$btnStart.Add_Click({
    if ($script:Running) { return }
    $script:Running = $true; $script:StartTime = Get-Date; $script:SessionSec = 0
    $btnStart.Enabled = $false; $btnStop.Enabled = $true
    $lStatus.Text = '▶  Running...'; $lStatus.ForeColor = $GREEN; $lTimer.ForeColor = $GOLD
})

$btnStop.Add_Click({
    if (-not $script:Running) { return }
    $script:Running = $false; $end = Get-Date; $secs = $script:SessionSec
    if ($cmbCat.SelectedItem) { $cat = $cmbCat.SelectedItem.ToString() } else { $cat = 'General Support' }
    $desc = $txtDesc.Text.Trim(); if (-not $desc) {$desc='(no description)'}
    Save-Session $cat $desc $script:StartTime $end $secs | Out-Null
    Refresh-ListView; Render-Calendar
    $script:SessionSec = 0; $lTimer.Text = '00:00:00'; $lTimer.ForeColor = $WHITE
    $lStatus.Text = "⏸  Last: $(Format-Dur $secs)"; $lStatus.ForeColor = $MUTED
    $btnStart.Enabled = $true; $btnStop.Enabled = $false
    $txtDesc.Clear(); $cmbCat.SelectedIndex = 0
})

$btnManual.Add_Click({
    # ── Manual Entry Dialog ───────────────────────────────────────────────────
    $dlg = New-Object System.Windows.Forms.Form
    $dlg.Text = 'Manual Time Entry'
    $dlg.Size = New-Object System.Drawing.Size(400, 340)
    $dlg.StartPosition = 'CenterParent'
    $dlg.BackColor = $NAVY; $dlg.ForeColor = $WHITE
    $dlg.FormBorderStyle = 'FixedDialog'; $dlg.MaximizeBox = $false; $dlg.MinimizeBox = $false
    $dlg.Font = New-Object System.Drawing.Font('Segoe UI', 9)

    function DlgLabel($text,$x,$y) {
        $l = New-Object System.Windows.Forms.Label; $l.Text = $text
        $l.Font = New-Object System.Drawing.Font('Segoe UI',7,[System.Drawing.FontStyle]::Bold)
        $l.ForeColor = $MAUVE; $l.Location = New-Object System.Drawing.Point($x,$y); $l.Size = New-Object System.Drawing.Size(180,16)
        $dlg.Controls.Add($l)
    }

    function DlgTextBox($x,$y,$w,$val) {
        $t = New-Object System.Windows.Forms.TextBox; $t.Text = $val
        $t.Location = New-Object System.Drawing.Point($x,$y); $t.Size = New-Object System.Drawing.Size($w,26)
        $t.BackColor = $NAVY3; $t.ForeColor = $WHITE; $t.BorderStyle = 'FixedSingle'
        $dlg.Controls.Add($t); return $t
    }

    DlgLabel 'DATE (yyyy-MM-dd)' 12 12
    $tDate = DlgTextBox 12 30 180 ((Get-Date).ToString('yyyy-MM-dd'))

    DlgLabel 'START TIME (HH:MM)' 12 64
    $tStart = DlgTextBox 12 82 80 '09:00'

    DlgLabel 'END TIME (HH:MM)' 110 64
    $tEnd = DlgTextBox 110 82 80 '10:00'

    DlgLabel 'CATEGORY' 12 116
    $cmbM = New-Object System.Windows.Forms.ComboBox
    $cmbM.Location = New-Object System.Drawing.Point(12,134); $cmbM.Size = New-Object System.Drawing.Size(360,26)
    $cmbM.DropDownStyle = 'DropDownList'; $cmbM.BackColor = $NAVY3; $cmbM.ForeColor = $WHITE; $cmbM.FlatStyle = 'Flat'
    $CATEGORIES | ForEach-Object { [void]$cmbM.Items.Add($_) }; $cmbM.SelectedIndex = 0
    $dlg.Controls.Add($cmbM)

    DlgLabel 'DESCRIPTION' 12 168
    $tDesc = New-Object System.Windows.Forms.TextBox
    $tDesc.Location = New-Object System.Drawing.Point(12,186); $tDesc.Size = New-Object System.Drawing.Size(360,50)
    $tDesc.Multiline = $true; $tDesc.BackColor = $NAVY3; $tDesc.ForeColor = $WHITE; $tDesc.BorderStyle = 'FixedSingle'
    $dlg.Controls.Add($tDesc)

    $lErr = New-Object System.Windows.Forms.Label; $lErr.ForeColor = [System.Drawing.Color]::FromArgb(220,53,69)
    $lErr.Location = New-Object System.Drawing.Point(12,244); $lErr.Size = New-Object System.Drawing.Size(360,18)
    $lErr.Font = New-Object System.Drawing.Font('Segoe UI',8); $dlg.Controls.Add($lErr)

    $btnSave   = New-Btn2 'Save Entry'   12  265  170  38  $GREEN $WHITE
    $btnCancel = New-Btn2 'Cancel'      196  265  176  38  $NAVY3 $MUTED
    $dlg.Controls.AddRange(@($btnSave,$btnCancel))

    $btnCancel.Add_Click({ $dlg.Close() })

    $btnSave.Add_Click({
        $lErr.Text = ''
        # Validate
        $dateOk  = $false; $startOk = $false; $endOk = $false
        try { $parsedDate  = [datetime]::ParseExact($tDate.Text.Trim(),'yyyy-MM-dd',$null); $dateOk  = $true } catch {}
        try { $parsedStart = [datetime]::ParseExact($tStart.Text.Trim(),'HH:mm',$null);     $startOk = $true } catch {}
        try { $parsedEnd   = [datetime]::ParseExact($tEnd.Text.Trim(),'HH:mm',$null);       $endOk   = $true } catch {}

        if (-not $dateOk)  { $lErr.Text = 'Invalid date — use yyyy-MM-dd'; return }
        if (-not $startOk) { $lErr.Text = 'Invalid start time — use HH:MM (24hr)'; return }
        if (-not $endOk)   { $lErr.Text = 'Invalid end time — use HH:MM (24hr)'; return }

        $startDT = $parsedDate.Date + $parsedStart.TimeOfDay
        $endDT   = $parsedDate.Date + $parsedEnd.TimeOfDay
        if ($endDT -le $startDT) { $lErr.Text = 'End time must be after start time'; return }

        $secs = ($endDT - $startDT).TotalSeconds
        $cat  = $cmbM.SelectedItem.ToString()
        $desc = $tDesc.Text.Trim(); if (-not $desc) { $desc = '(manual entry)' }

        Save-Session $cat $desc $startDT $endDT $secs | Out-Null
        Refresh-ListView; Render-Calendar
        $dlg.Close()
    })

    [void]$dlg.ShowDialog($form)
})

$btnExport.Add_Click({
    $dlg = New-Object System.Windows.Forms.SaveFileDialog
    $dlg.Filter = 'CSV Files (*.csv)|*.csv'
    $dlg.FileName = "RuffLife-TimeLog-$(Get-Date -Format 'yyyy-MM-dd').csv"
    $dlg.InitialDirectory = $SCRIPT_DIR
    if ($dlg.ShowDialog() -eq 'OK') {
        Copy-Item $LOG_FILE $dlg.FileName -Force
        [System.Windows.Forms.MessageBox]::Show("Exported to:`n$($dlg.FileName)",'Export','OK','Information') | Out-Null
    }
})

$form.Add_FormClosing({
    param($s,$e)
    if ($script:Running) {
        $ans = [System.Windows.Forms.MessageBox]::Show('Timer running. Save before closing?','Timer Running','YesNoCancel','Warning')
        if ($ans -eq 'Yes') {$btnStop.PerformClick()} elseif ($ans -eq 'Cancel') {$e.Cancel=$true}
    }
})

$form.Add_KeyDown({
    param($s,$e)
    if ($e.KeyCode -eq 'F5' -and $btnStart.Enabled) {$btnStart.PerformClick()}
    if ($e.KeyCode -eq 'F6' -and $btnStop.Enabled)  {$btnStop.PerformClick()}
})

Load-Log; Refresh-ListView; Render-Calendar
[void]$form.ShowDialog()