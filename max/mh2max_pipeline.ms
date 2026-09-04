-- mh2max_pipeline.ms
-- Generic MetaHuman Max assembly. Driven by globals from mh2max_job.ms.
-- No Max UI / bone-toggle buttons.
--
-- v1.3.31:
--   * Maya Y-up FBX → Max Z-up via FBX AxisConversion on all roots
--     (meshes / joints / controllers / IK / Skin stay in one converted hierarchy).
--   * Morph OBJ already rotate -90 X; do not convert FBX as Y-up or the character lies down.
-- v1.3.29:
--   * Revert Max-side body controller wiring (mh2max_body_drive / Pos/Ori / IK chains).
-- v1.3.28:
--   * Force consistent FBX import settings to avoid cross-run distortion.
--   * Avoid "$" selection when importing morph OBJs; find newly imported object by diff.
--
-- Slider limits v5 (one-click export):
--   * All FRM sliders incl. lookAt/rigLogic/convergence/followHead get float_limit
--   * Unused axes pinned 0..0 (both enables); segments honor Maya elo/ehi as-is
--   * FreezeTransform only after snap to parent origin; FROZEN forced to [0,0,0]
--   * Soft clamp folds any FROZEN drift back into ZERO_POS
--   * Never scale CTRL knobs for pickability
-- Viewport v5:
--   * Perspective user view framed on head + face GUI (no scene camera left behind)

if mh2max_outDir == undefined then throw "mh2max_outDir missing — run the Maya-generated job.ms"
if mh2max_fbx == undefined then throw "mh2max_fbx missing"

mxOutDir = mh2max_outDir
mxFbx = mh2max_fbx
mxMorphDir = mh2max_morphDir
mxLimits = mh2max_limits
mxLog = mh2max_log
mxSaveBase = undefined
if mh2max_saveBase != undefined then mxSaveBase = mh2max_saveBase as string
else if mh2max_save != undefined then (
    -- legacy job.ms: strip trailing .max from single save path
    local legacy = mh2max_save as string
    if (matchPattern legacy pattern:"*.max") then mxSaveBase = substring legacy 1 (legacy.count - 4)
    else mxSaveBase = legacy
)
if mxSaveBase == undefined then throw "mh2max_saveBase missing — re-export job.ms from Maya"
mxHeadName = if mh2max_head == undefined then "head_lod0_mesh" else mh2max_head
mxBodyName = if mh2max_body == undefined then "" else mh2max_body
mxBodyGrpName = if mh2max_bodyGrp == undefined then "body_lod0_grp" else mh2max_bodyGrp
mxHeadGrpName = if mh2max_headGrp == undefined then "head_grp" else mh2max_headGrp
mxGuiName = if mh2max_gui == undefined then "CTRL_faceGUI" else mh2max_gui
mxGuiGrpName = if mh2max_guiGrp == undefined then "GRP_faceGUI" else mh2max_guiGrp
mxCombinedName = if mh2max_combined == undefined then "" else mh2max_combined

fn logf msg = (
    local f = openFile mxLog mode:"a"
    if f == undefined then f = createFile mxLog
    format "%\n" msg to:f
    close f
)

-- Map maxVersion()[1] (e.g. 28000) to calendar year (e.g. 2026).
fn mh2max_getMaxYear = (
    (maxVersion())[1] / 1000 + 1998
)

-- Max 2026+ splits Render Output Defaults for #GammaEncoded vs #Linear file types.
-- saveAsVersion:2024 rejects scenes where those two differ — align both to #NoConversion
-- before down-saving, then restore the artist's settings.
fn mh2max_getOutputConv fileType = (
    local cs = ""
    local disp = ""
    local vt = ""
    local conv = undefined
    try (
        if fileType == #Linear then (
            conv = ColorPipelineMgr.GetDefaultOutputConversion fileType:#Linear colorSpace:&cs display:&disp viewTransform:&vt
        ) else (
            conv = ColorPipelineMgr.GetDefaultOutputConversion fileType:#GammaEncoded colorSpace:&cs display:&disp viewTransform:&vt
        )
    ) catch (
        conv = ColorPipelineMgr.GetDefaultOutputConversion colorSpace:&cs display:&disp viewTransform:&vt
    )
    #(conv, cs, disp, vt)
)

fn mh2max_setOutputConv state fileType = (
    if state == undefined or state[1] == undefined then return false
    local conv = state[1]
    local cs = state[2]
    local disp = state[3]
    local vt = state[4]
    try (
        if conv == #NoConversion then (
            if fileType == #Linear then ColorPipelineMgr.SetDefaultOutputConversion #NoConversion fileType:#Linear
            else ColorPipelineMgr.SetDefaultOutputConversion #NoConversion fileType:#GammaEncoded
        ) else if conv == #ColorSpaceConversion then (
            if fileType == #Linear then ColorPipelineMgr.SetDefaultOutputConversion #ColorSpaceConversion fileType:#Linear colorSpace:cs
            else ColorPipelineMgr.SetDefaultOutputConversion #ColorSpaceConversion fileType:#GammaEncoded colorSpace:cs
        ) else if conv == #DisplayViewtransform then (
            if fileType == #Linear then ColorPipelineMgr.SetDefaultOutputConversion #DisplayViewtransform fileType:#Linear colorSpace:cs display:disp viewTransform:vt
            else ColorPipelineMgr.SetDefaultOutputConversion #DisplayViewtransform fileType:#GammaEncoded colorSpace:cs display:disp viewTransform:vt
        )
        true
    ) catch (
        if conv == #NoConversion then ColorPipelineMgr.SetDefaultOutputConversion #NoConversion
        else if conv == #ColorSpaceConversion then ColorPipelineMgr.SetDefaultOutputConversion #ColorSpaceConversion colorSpace:cs
        else ColorPipelineMgr.SetDefaultOutputConversion #DisplayViewtransform colorSpace:cs display:disp viewTransform:vt
    )
)

fn mh2max_alignOutputConvForDownSave = (
    ColorPipelineMgr.SetDefaultOutputConversion #NoConversion fileType:#GammaEncoded
    try ( ColorPipelineMgr.SetDefaultOutputConversion #NoConversion fileType:#Linear ) catch ()
    true
)

fn mh2max_trySaveAs2024 path2024 = (
    local gammaB = mh2max_getOutputConv #GammaEncoded
    local linearB = undefined
    try ( linearB = mh2max_getOutputConv #Linear ) catch ()
    local wasQuiet = setQuietMode true
    local ok = false
    try (
        mh2max_alignOutputConvForDownSave()
        ok = saveMaxFile path2024 saveAsVersion:2024 quiet:true
        if ok then logf ("saved " + path2024 + " (saveAsVersion:2024)")
        else logf ("saveAsVersion 2024 returned false for " + path2024)
    ) catch (
        logf ("saveAsVersion 2024 skipped: " + (getCurrentException() as string))
        ok = false
    )
    try ( mh2max_setOutputConv gammaB #GammaEncoded ) catch ()
    if linearB != undefined then (
        try ( mh2max_setOutputConv linearB #Linear ) catch ()
    )
    setQuietMode wasQuiet
    ok
)

-- Archive rigged scene: always write current Max year; when host > 2024 also try
-- saveAsVersion:2024. Host already 2024 -> single _max2024.max only.
fn mh2max_saveArchives basePath = (
    local saved = #()
    local curYear = mh2max_getMaxYear()
    local curPath = basePath + "_max" + (curYear as string) + ".max"

    if curYear == 2024 then (
        curPath = basePath + "_max2024.max"
        saveMaxFile curPath quiet:true
        append saved curPath
        logf ("saved " + curPath)
        return saved
    )

    saveMaxFile curPath quiet:true
    append saved curPath
    logf ("saved " + curPath)

    if curYear > 2024 then (
        local path2024 = basePath + "_max2024.max"
        if mh2max_trySaveAs2024 path2024 then append saved path2024
    )
    saved
)

-- Real-time progress overlay (non-modal). Editing suspended so user cannot work the scene.
rollout mh2max_ProgressRO "mh2max" width:460 height:126
(
    label lblTitle "MetaHuman → 3ds Max 装配中" align:#center width:440
    label lblStatus "准备…" align:#left width:440 height:44
    progressBar pb value:0 color:(color 40 130 220) width:430 height:28
    label lblPct "0 %" align:#right width:440
)

fn mh2max_uiPump = (
    try ( windows.processPostedMessages() ) catch ()
)

fn mh2max_progBegin = (
    try ( if mh2max_ProgressRO.open do destroyDialog mh2max_ProgressRO ) catch ()
    createDialog mh2max_ProgressRO style:#(#style_toolwindow) escapeEnable:false modal:false
    try (
        local wh = getMAXWindowSize()
        setDialogPos mh2max_ProgressRO [((wh.x - 460) / 2), ((wh.y - 126) / 2)]
    ) catch ()
    -- Do NOT disableSceneRedraw / progressStart here: kills Nitrous viewports when
    -- launched via -U MAXScript before UI finishes initializing.
    try ( suspendEditing() ) catch ()
    try ( setWaitCursor() ) catch ()
    mh2max_uiPump()
)

fn mh2max_prog pct msg = (
    local p = pct as integer
    if p < 0 then p = 0
    if p > 100 then p = 100
    try (
        if mh2max_ProgressRO.open do (
            mh2max_ProgressRO.pb.value = p
            mh2max_ProgressRO.lblStatus.text = msg
            mh2max_ProgressRO.lblPct.text = ((p as string) + " %")
        )
    ) catch ()
    try ( pushPrompt ("mh2max " + (p as string) + "% — " + msg) ) catch ()
    try ( logf ("PROG " + (p as string) + "% " + msg) ) catch ()
    mh2max_uiPump()
)

fn mh2max_progEnd = (
    try ( resumeEditing() ) catch ()
    try ( setArrowCursor() ) catch ()
    try ( if mh2max_ProgressRO.open do destroyDialog mh2max_ProgressRO ) catch ()
    try ( popPrompt() ) catch ()
    try ( enableSceneRedraw() ) catch ()
    try ( completeRedraw() ) catch ()
    try ( redrawViews() ) catch ()
    mh2max_uiPump()
)

fn nodeBy n = (
    if n == undefined or n.count == 0 then return undefined
    getNodeByName n
)

fn findByPattern pat = (
    for o in objects do (
        if matchPattern o.name pattern:pat ignoreCase:true then return o
    )
    undefined
)

fn findBodyMesh = (
    local o = nodeBy mxBodyName
    if o != undefined then return o
    o = findByPattern "*_body_lod0_mesh"
    if o != undefined then return o
    for g in geometry do (
        if (matchPattern g.name pattern:"*body*lod0*" ignoreCase:true) and (not matchPattern g.name pattern:"*combined*" ignoreCase:true) and (not matchPattern g.name pattern:"*flipflop*" ignoreCase:true) then return g
    )
    undefined
)

fn findCombinedMesh = (
    local o = nodeBy mxCombinedName
    if o != undefined then return o
    findByPattern "*_combined_lod0_mesh"
)

fn isAncestor a b = (
    local o = b
    while o != undefined do (
        if o == a then return true
        o = o.parent
    )
    false
)

fn keepWorldParent driven driver = (
    in coordsys world (
        local tm = driven.transform
        driven.parent = driver
        driven.transform = tm
    )
)

fn detachKeepWorld obj = (
    if obj == undefined or obj.parent == undefined then return false
    in coordsys world (
        local tm = obj.transform
        obj.parent = undefined
        obj.transform = tm
    )
    true
)

fn wireBodyLinksFromFile = (
    -- v1.3.29: reverted body controller optimizations (v1.3.12–v1.3.28).
    -- Body rig comes from FBX import only; face still uses Morph + CTRL_* wiring.
    logf "body wire: skipped (body drive disabled)"
    0
)

fn ensureLayer nm = (
    local ly = LayerManager.getLayerFromName nm
    if ly == undefined then ly = LayerManager.newLayerFromName nm
    ly
)

fn parseMorphName n = (
    local name = n
    -- Keep in sync with Maya detect.MORPH_PREFIXES / MESH_JOBS (non-Face folders)
    local prefixes = #("Teeth_", "Saliva_", "EyeLeft_", "EyeRight_", "EyeLash_", "EyeShell_", "EyeEdge_", "Cartilage_")
    for pref in prefixes do (
        if matchPattern name pattern:(pref + "*") then (
            name = substring name (pref.count + 1) name.count
            exit
        )
    )
    -- Corner combo residual: "<ctrl>.comboX<sx>Y<sy>" (bilinear corrective)
    local pc = findString name ".combo"
    if pc != undefined then (
        local ctrl = substring name 1 (pc - 1)
        local s = substring name (pc + 6) name.count -- e.g. "X-1Y1"
        local yp = findString s "Y"
        if yp == undefined then return undefined
        local sx = (substring s 2 (yp - 2)) as integer
        local sy = (substring s (yp + 1) (s.count - yp)) as integer
        if sx == undefined or sy == undefined then return undefined
        return #(ctrl, "COMBO", #(sx, sy))
    )
    local p = findString name ".translate"
    if p == undefined then return undefined
    local ctrl = substring name 1 (p - 1)
    local axisVal = substring name (p + 10) name.count
    local axis = substring axisVal 1 1
    local valStr = substring axisVal 2 axisVal.count
    local poseVal = valStr as integer
    #(ctrl, axis, poseVal)
)

-- One-click morph mesh table (Maya MESH_JOBS). Face has empty prefix.
-- #(prefix, meshName, label)
-- Job file may set mh2max_morphMeshJobsOverride before fileIn (custom standardized meshes).
global mh2max_morphMeshJobsOverride
global mh2max_morphMeshJobs = #(
    #("", "head_lod0_mesh", "face"),
    #("Teeth_", "teeth_lod0_mesh", "teeth"),
    #("Saliva_", "saliva_lod0_mesh", "saliva"),
    #("EyeLeft_", "eyeLeft_lod0_mesh", "eyeLeft"),
    #("EyeRight_", "eyeRight_lod0_mesh", "eyeRight"),
    #("EyeLash_", "eyelashes_lod0_mesh", "eyeLash"),
    #("EyeShell_", "eyeshell_lod0_mesh", "eyeShell"),
    #("EyeEdge_", "eyeEdge_lod0_mesh", "eyeEdge"),
    #("Cartilage_", "cartilage_lod0_mesh", "cartilage")
)
if mh2max_morphMeshJobsOverride != undefined and (classOf mh2max_morphMeshJobsOverride) == Array then (
    mh2max_morphMeshJobs = mh2max_morphMeshJobsOverride
    format "mh2max: morph mesh jobs override count=%\n" mh2max_morphMeshJobs.count
)

fn mh2max_resolveMesh nm = (
    local n = nodeBy nm
    if n == undefined then n = findByPattern ("*" + nm)
    n
)

fn mh2max_clearMorphersOn meshNode = (
    if meshNode == undefined then return false
    for i = meshNode.modifiers.count to 1 by -1 do (
        if classof meshNode.modifiers[i] == Morpher then deleteModifier meshNode i
    )
    true
)

fn mh2max_cmpMorph a b = stricmp a.name b.name

fn mh2max_bucketMorphTargets = (
    -- Returns array parallel to mh2max_morphMeshJobs: each entry is #(mesh, targetsArray)
    local buckets = #()
    if (classOf mh2max_morphMeshJobs) != Array or mh2max_morphMeshJobs.count == 0 then (
        logf "WARN mh2max_morphMeshJobs is empty; skipping morph bucketing"
        return buckets
    )
    for j = 1 to mh2max_morphMeshJobs.count do (
        local job = mh2max_morphMeshJobs[j]
        local meshNode = mh2max_resolveMesh job[2]
        mh2max_clearMorphersOn meshNode
        append buckets #(meshNode, #())
    )
    for o in objects do (
        if (findString o.name ".translate") != undefined or (findString o.name ".combo") != undefined then (
            local placed = false
            -- Prefixed jobs first (index 2..n); Face (index 1) is the fallback
            for j = 2 to mh2max_morphMeshJobs.count do (
                local pref = mh2max_morphMeshJobs[j][1]
                if matchPattern o.name pattern:(pref + "*") then (
                    append buckets[j][2] o
                    placed = true
                    exit
                )
            )
            if not placed then append buckets[1][2] o
        )
    )
    for j = 1 to buckets.count do (
        qsort buckets[j][2] mh2max_cmpMorph
    )
    buckets
)

fn getAxisCtrl src axis = (
    local key = if axis == "X" or axis == "x" then #X_Position else if axis == "Y" or axis == "y" then #Y_Position else #Z_Position
    -- Prefer Limited_Controller bezier_float inside float_limit (not the SubAnim wrapper)
    try (
        local lim = src.pos.controller.ZERO_POS_XYZ.controller[key].controller
        if classOf lim == Float_Limit or classOf lim == float_limit then (
            try (
                local sa = lim[#Limited_Controller__Bezier_Float]
                if sa != undefined then (
                    try ( if sa.controller != undefined then return sa.controller ) catch ()
                    return sa
                )
            ) catch ()
            -- Chinese Max: subAnim 1 = 限制控制器__Bezier_浮点
            try ( if lim[1] != undefined and lim[1].controller != undefined then return lim[1].controller ) catch ()
            return lim
        )
    ) catch ()
    try ( return src.pos.controller.ZERO_POS_XYZ.controller[key] ) catch ()
    try ( return src.pos.controller[key] ) catch ()
    undefined
)

-- Bone wires: prefer float_limit (GUI 0..1). Morph wires keep getAxisCtrl (inner bezier).
fn getLimitCtrl src axis = (
    if src == undefined then return undefined
    local key = if axis == "X" or axis == "x" then #X_Position else if axis == "Y" or axis == "y" then #Y_Position else #Z_Position
    try (
        local lim = src.pos.controller.ZERO_POS_XYZ.controller[key].controller
        if classOf lim == Float_Limit or classOf lim == float_limit then return lim
    ) catch ()
    getAxisCtrl src axis
)

-- Rebuild MetaHuman-style Position_List + Rotation_list (exact conversion-tool FreezeTransform).
fn freezeTransformOne CurObj = (
    if CurObj == undefined then return false
    local curRotCtrl = CurObj.rotation.controller
    if classof curRotCtrl != Rotation_Layer do (
        local activeCtrl = undefined
        if (classof curRotCtrl == Rotation_list) do (
            if (curRotCtrl.getCount() == 2 and curRotCtrl.getActive() == 2 and classof curRotCtrl[2].controller == Euler_Xyz) do (
                activeCtrl = curRotCtrl[2]
            )
        )
        CurObj.rotation.controller = Euler_Xyz()
        CurObj.rotation.controller = Rotation_list()
        if (activeCtrl != undefined) then (
            activeCtrl.x_rotation = 0
            activeCtrl.y_rotation = 0
            activeCtrl.z_rotation = 0
            CurObj.rotation.controller.available.controller = activeCtrl.controller
        ) else (
            CurObj.rotation.controller.available.controller = Euler_xyz()
        )
        CurObj.rotation.controller.setname 1 "FROZEN_ROTATION"
        CurObj.rotation.controller.setname 2 "ZERO_EULER_XYZ"
        CurObj.rotation.controller.SetActive 2
        try ( setAppData (CurObj.rotation.controller[1].controller) 0x100 "InternalFlagByFreezeTransform" ) catch ()
    )
    local curPosCtrl = CurObj.position.controller
    if classof curPosCtrl != Position_Layer do (
        local activeCtrl = undefined
        if (classof curPosCtrl == position_list) do (
            if (curPosCtrl.getCount() == 2 and curPosCtrl.getActive() == 2 and classof curPosCtrl[2].controller == Position_XYZ) do (
                activeCtrl = curPosCtrl[2]
            )
        )
        CurObj.position.controller = Bezier_Position()
        CurObj.position.controller = position_list()
        if (activeCtrl != undefined) then (
            activeCtrl.x_position = 0
            activeCtrl.y_position = 0
            activeCtrl.z_position = 0
            CurObj.position.controller.available.controller = activeCtrl.controller
        ) else (
            CurObj.position.controller.available.controller = Position_XYZ()
        )
        CurObj.position.controller.setname 1 "FROZEN_POSITION"
        CurObj.position.controller.setname 2 "ZERO_POS_XYZ"
        CurObj.position.controller.SetActive 2
        CurObj.Position.controller[2].x_Position = 0
        CurObj.Position.controller[2].y_Position = 0
        CurObj.Position.controller[2].z_Position = 0
        try ( setAppData (CurObj.position.controller[1].controller) 0x100 "InternalFlagByFreezeTransform" ) catch ()
    )
    true
)

fn ensureZeroPosXYZ ctrl = (
    if ctrl == undefined then return false
    local pc = ctrl.pos.controller
    try (
        if (classOf pc == Position_List or classOf pc == position_list) then (
            local nm2 = try (pc.getName 2) catch ("")
            if (nm2 as string) == "ZERO_POS_XYZ" then (
                try ( pc.SetActive 2 ) catch ()
                return true
            )
        )
    ) catch ()
    freezeTransformOne ctrl
)

fn getZeroPosXYZ ctrl = (
    try ( return ctrl.pos.controller.ZERO_POS_XYZ.controller ) catch ()
    try ( return ctrl.Position.controller[2].controller ) catch ()
    undefined
)

fn setLimitedAxisValue zp key v = (
    try (
        local lim = zp[key].controller
        if classOf lim == Float_Limit or classOf lim == float_limit then (
            try ( lim[#Limited_Controller__Bezier_Float].value = v; return true ) catch ()
            try ( lim.value = v; return true ) catch ()
        )
    ) catch ()
    try ( zp[key].value = v; return true ) catch ()
    false
)

-- MUST be defined before freezeGuiDecor (MaxScript can resolve as undefined otherwise)
fn isSliderCtrl nm = (
    if nm == undefined or nm == "" then return false
    if findString nm "CTRL_" != 1 then return false
    -- Board roots / non-sliders only (switch + followHead sliders MUST get limits)
    local skip = #(
        "CTRL_faceGUI", "CTRL_faceTweakersGUI",
        "CTRL_faceAndEyesAimFollowHeadGUI", "CTRL_expressions", "CTRL_rigLogic",
        "CTRL_GUIswitch"
    )
    if findItem skip nm > 0 then return false
    if matchPattern nm pattern:"CTRL_neckCorrectives*" then return false
    true
)

fn isGuiFollowSlider nm = (
    nm == "CTRL_faceGUIfollowHead" or nm == "CTRL_eyesAimFollowHead"
)

-- Viewport drag often bypasses float_limit. Soft clamp via #nodePostTransform only
-- (per-node when-transform storms can black out Max UI).
global mh2max_clampBusy = false
global mh2max_clampCtrls = #()

fn applyLimitFloat ctrl axisName lower upper eLo eHi = (
    -- Assumes FreezeTransform / ZERO_POS already present on ctrl
    try ( ctrl.pos.controller.SetActive 2 ) catch ()
    local key = case axisName of (
        "x": #X_Position
        "y": #Y_Position
        "z": #Z_Position
        default: #X_Position
    )
    local zp = getZeroPosXYZ ctrl
    if zp == undefined then throw ("no ZERO_POS_XYZ " + ctrl.name)
    zp[key].controller = float_limit()
    local lim = zp[key].controller
    try ( lim.enable = true ) catch ()
    try ( lim.SetEnabled true ) catch ()
    if eLo == 0 and eHi == 0 then (
        -- Maya "axis unused": pin hard to 0 (do NOT leave float_limit disabled —
        -- viewport/parent-space drag otherwise writes huge values on locked axes).
        lim.lower_limit = 0.0
        lim.upper_limit = 0.0
        lim.lower_limit_enabled = true
        lim.upper_limit_enabled = true
        setLimitedAxisValue zp key 0.0
    ) else (
        -- Segment or true one-sided Maya limit: honor enable flags exactly.
        -- One-sided range like Y=0..1 with both enables is a SEGMENT (looks like a ray in FRM).
        lim.lower_limit = lower
        lim.upper_limit = upper
        lim.lower_limit_enabled = (eLo == 1)
        lim.upper_limit_enabled = (eHi == 1)
        setLimitedAxisValue zp key 0.0
    )
    true
)

fn isFaceOriginalCtrl o = (
    -- Custom face BS drivers are named *_Ctrl under FRM_* (or have a CTRL_* proxy).
    -- Body / IK / FK controllers are also often *_Ctrl — must NOT freeze those.
    if o == undefined then return false
    local nm = o.name
    if not (matchPattern nm pattern:"*_Ctrl") then return false
    if matchPattern nm pattern:"CTRL_*" then return false
    if o.parent != undefined and (matchPattern o.parent.name pattern:"FRM_*") then return true
    -- proxy naming: R_mouth_cornerPull_Ctrl → CTRL_R_mouth_cornerPull
    if nm.count > 5 then (
        local stem = substring nm 1 (nm.count - 5)
        local proxy = getNodeByName ("CTRL_" + stem) exact:true ignoreCase:false
        if proxy != undefined then return true
    )
    false
)

fn freezeGuiDecor = (
    -- Freeze panel frames / labels; keep slider CTRL_* knobs selectable.
    -- Hide only face original *_Ctrl (Maya BS drivers) — Morph wires to CTRL_*.
    -- Do NOT freeze body / IK / FK *_Ctrl (Master_Ctrl, COG_Ctrl, etc.).
    local n = 0
    mh2max_clampBusy = true
    clearSelection()
    for o in objects do (
        local nm = o.name
        local doFreeze = false
        local doHide = false
        if matchPattern nm pattern:"FRM_*" then doFreeze = true
        else if matchPattern nm pattern:"TEXT_*" then doFreeze = true
        else if matchPattern nm pattern:"GRP_faceGUI*" then doFreeze = true
        else if matchPattern nm pattern:"GRP_faceTweakers*" then doFreeze = true
        else if nm == "CTRL_faceGUI" then doFreeze = true
        else if nm == "CTRL_faceTweakersGUI" then doFreeze = true
        else if (isGuiFollowSlider nm) then doFreeze = false
        else if matchPattern nm pattern:"CTRL_*GUI*" and not (::isSliderCtrl nm) then doFreeze = true
        else if (isFaceOriginalCtrl o) then (
            doFreeze = true
            doHide = true
        )
        else if (classOf o == Text or classOf o == text or classOf o == Shape or classOf o == Editable_Spline or classOf o == line or classOf o == Line) then (
            -- decor curves only — never body controllers named *_Ctrl
            if (not matchPattern nm pattern:"CTRL_*") and (not matchPattern nm pattern:"*_Ctrl") then doFreeze = true
        )
        if doFreeze then (
            try ( freeze o ) catch ()
            try ( setTransformLockFlags o #{1,2,3,4,5,6,7,8,9} ) catch ()
            n += 1
        )
        if doHide then (try ( hide o ) catch ())
    )
    for o in objects do (
        if (::isSliderCtrl o.name) or (isGuiFollowSlider o.name) then (
            try ( unfreeze o ) catch ()
            try ( unhide o ) catch ()
            try ( setTransformLockFlags o #{} ) catch ()
        )
        else if (matchPattern o.name pattern:"*_Ctrl") and (not matchPattern o.name pattern:"CTRL_*") and (not (isFaceOriginalCtrl o)) then (
            -- restore body / IK / FK controllers if an older pipeline froze them
            try ( unfreeze o ) catch ()
            try ( unhide o ) catch ()
            try ( setTransformLockFlags o #{} ) catch ()
        )
    )
    mh2max_clampBusy = false
    n
)

fn mh2max_deleteNodeByName nm = (
    local o = getNodeByName nm exact:true ignoreCase:false
    if o != undefined then (try ( delete o ) catch ())
)

fn mh2max_guessFaceForward head = (
    -- GUI is placed on +X of head; MetaHuman FBX typically faces -Y
    local fwd = [0, -1, 0]
    try (
        local ly = head.transform.row2
        local horiz = normalize [ly.x, ly.y, 0]
        if length horiz > 0.25 then fwd = -horiz
    ) catch ()
    if length fwd < 0.1 then fwd = [0, -1, 0]
    normalize fwd
)

fn mh2max_faceLookAtPoint head = (
    local hmin = head.min
    local hmax = head.max
    local faceC = [(hmin.x + hmax.x) * 0.5, (hmin.y + hmax.y) * 0.5, hmin.z + (hmax.z - hmin.z) * 0.60]
    local el = nodeBy "eyeLeft_lod0_mesh"
    local er = nodeBy "eyeRight_lod0_mesh"
    if el == undefined then el = findByPattern "*eyeLeft*lod0*"
    if er == undefined then er = findByPattern "*eyeRight*lod0*"
    if el != undefined and er != undefined then (
        faceC = (((el.min + el.max) * 0.5) + ((er.min + er.max) * 0.5)) * 0.5
    )
    faceC
)

fn mh2max_deleteFaceCameras = (
    for nm in #("mh2max_faceCam", "mh2max_faceTgt") do (
        local o = getNodeByName nm exact:true ignoreCase:false
        if o != undefined then (try ( delete o ) catch ())
    )
    -- Also sweep any leftover Targetcamera named like ours
    for o in cameras do (
        try (
            if matchPattern o.name pattern:"mh2max_face*" then (
                try ( if o.target != undefined then delete o.target ) catch ()
                try ( delete o ) catch ()
            )
        ) catch ()
    )
    true
)

fn mh2max_expandBBox bmin bmax o = (
    if o == undefined or not (isValidNode o) then return #(bmin, bmax)
    local omin = o.min
    local omax = o.max
    #(
        [amin #(bmin.x, omin.x), amin #(bmin.y, omin.y), amin #(bmin.z, omin.z)],
        [amax #(bmax.x, omax.x), amax #(bmax.y, omax.y), amax #(bmax.z, omax.z)]
    )
)

fn mh2max_collectFaceFrameNodes head = (
    -- Head + face GUI board / knobs / frames so Zoom framing includes all controllers
    local nodes = #()
    if head != undefined and (isValidNode head) then append nodes head
    for nm in #(
        mxGuiName, mxGuiGrpName,
        "CTRL_faceTweakersGUI", "GRP_faceTweakersGUI", "GRP_faceTweakers",
        "CTRL_faceAndEyesAimFollowHeadGUI", "FRM_faceAndEyesAimFollowHeadGUI",
        "GRP_faceGUI", "FRM_faceGUI"
    ) do (
        local o = nodeBy nm
        if o != undefined then appendIfUnique nodes o
    )
    for o in objects do (
        local nm = o.name
        if matchPattern nm pattern:"CTRL_*" and o.parent != undefined and (matchPattern o.parent.name pattern:"FRM_*") then (
            appendIfUnique nodes o
        ) else if matchPattern nm pattern:"FRM_*" then (
            appendIfUnique nodes o
        ) else if matchPattern nm pattern:"TEXT_*" then (
            appendIfUnique nodes o
        )
    )
    nodes
)

fn mh2max_setPerspLookAt eye target fov:36.0 = (
    -- Perspective user view (no scene camera). Max camera looks down local -Z.
    viewport.setType #view_persp_user
    local z = normalize (eye - target)
    if length z < 0.0001 then z = [0, 1, 0]
    local up = [0, 0, 1]
    local x = cross up z
    if length x < 0.001 then (
        up = [0, 1, 0]
        x = cross up z
    )
    x = normalize x
    local y = normalize (cross z x)
    local camTM = matrix3 x y z eye
    viewport.setTM (inverse camTM)
    try ( viewport.setFOV fov ) catch ()
    true
)

fn mh2max_frameFaceFront head = (
    -- Frame face + all face-board controllers in the active perspective viewport.
    -- Does NOT create or keep a scene camera.
    mh2max_deleteFaceCameras()
    if head == undefined then return false

    local nodes = mh2max_collectFaceFrameNodes head
    local bmin = head.min
    local bmax = head.max
    for o in nodes do (
        local bb = mh2max_expandBBox bmin bmax o
        bmin = bb[1]; bmax = bb[2]
    )
    local center = (bmin + bmax) * 0.5
    -- Prefer eye-height look-at when head is valid
    try (
        local faceC = mh2max_faceLookAtPoint head
        center = [center.x, center.y, faceC.z]
    ) catch ()

    local extentX = bmax.x - bmin.x
    local extentY = bmax.y - bmin.y
    local extentZ = bmax.z - bmin.z
    local extent = amax #(extentX, extentY, extentZ)
    if extent < 0.01 then extent = 10.0

    local fov = 36.0
    local half = extent * 0.55
    local dist = (half / (tan (DegToRad (fov * 0.5)))) * 1.20
    if dist < (extent * 1.2) then dist = extent * 1.2

    local fwd = mh2max_guessFaceForward head
    local eye = center - (fwd * dist)
    eye = [eye.x, eye.y, center.z]
    if distance eye center < (extent * 0.5) then (
        eye = center + [0, -dist, 0]
    )

    mh2max_setPerspLookAt eye center fov:fov

    -- Final fit: Zoom Extents Selected on head + GUI (keeps view direction)
    try (
        clearSelection()
        select nodes
        max zoomext sel
        clearSelection()
    ) catch (
        try (
            clearSelection()
            select head
            max zoomext sel
            clearSelection()
        ) catch ()
    )

    mh2max_deleteFaceCameras()
    try ( completeRedraw() ) catch ()
    true
)

fn mh2max_showOnlyRenderable keepNodes:#() = (
    -- Viewport: hide bones/helpers noise, but KEEP face/body controller shapes visible.
    try ( hideByCategory.bones = true ) catch ()
    try ( hideByCategory.helpers = true ) catch ()
    try ( hideByCategory.shapes = false ) catch () -- CTRL / FRM / *_Ctrl are Shapes
    try ( hideByCategory.lights = true ) catch ()
    try ( hideByCategory.warps = true ) catch ()
    try ( hideByCategory.particleSystems = true ) catch ()
    local nHide = 0
    local nShow = 0
    for o in objects do (
        local keep = false
        local nm = o.name
        for k in keepNodes where (k != undefined and isValidNode k) do (
            if o == k then keep = true
            try ( if o == k.target then keep = true ) catch ()
        )
        if (not keep) and nm != undefined and nm != "" then (
            if matchPattern nm pattern:"CTRL_*" then keep = true
            else if matchPattern nm pattern:"FRM_*" then keep = true
            else if matchPattern nm pattern:"*_Ctrl" then keep = true
            else if matchPattern nm pattern:"GRP_faceGUI*" then keep = true
            else if matchPattern nm pattern:"mh2max_*" then keep = true
        )
        if keep then (
            try ( unhide o ) catch ()
            nShow += 1
        ) else (
            local ren = true
            try ( ren = o.renderable ) catch ( ren = true )
            -- Hide non-mesh helpers; keep Geometry always
            if (superClassOf o == Helper) then ren = false
            if (classOf o == BoneGeometry) or (classOf o == Dummy) or (classOf o == Point) then ren = false
            -- Random shapes (not ctrl) stay hidden for clean viewport
            if (superClassOf o == Shape) then ren = false
            if ren then (
                try ( unhide o ) catch ()
                nShow += 1
            ) else (
                try ( hide o ) catch ()
                nHide += 1
            )
        )
    )
    #(nShow, nHide)
)

-- Viewport drag often bypasses float_limit (world/view coordsys). Clamp ZERO_POS after transform.
global mh2max_clampBusy = false
global mh2max_clampCtrls = #()

fn mh2max_parseLim ctrl = (
    local s = getUserProp ctrl "mh2max_lim"
    if s == undefined or s == "" then return undefined
    local p = filterString s ","
    if p.count < 12 then return undefined
    #(
        p[1] as float, p[2] as float, p[3] as integer, p[4] as integer,
        p[5] as float, p[6] as float, p[7] as integer, p[8] as integer,
        p[9] as float, p[10] as float, p[11] as integer, p[12] as integer
    )
)

fn mh2max_clampOne ctrl = (
    local lim = mh2max_parseLim ctrl
    if lim == undefined then return false
    local zp = getZeroPosXYZ ctrl
    if zp == undefined then return false
    local x = 0.0
    local y = 0.0
    local z = 0.0
    try (
        local lx = zp[#X_Position].controller
        if classOf lx == Float_Limit or classOf lx == float_limit then (
            try ( x = lx[#Limited_Controller__Bezier_Float].value ) catch ( x = lx.value )
        ) else x = zp[#X_Position].value
    ) catch ()
    try (
        local ly = zp[#Y_Position].controller
        if classOf ly == Float_Limit or classOf ly == float_limit then (
            try ( y = ly[#Limited_Controller__Bezier_Float].value ) catch ( y = ly.value )
        ) else y = zp[#Y_Position].value
    ) catch ()
    try (
        local lz = zp[#Z_Position].controller
        if classOf lz == Float_Limit or classOf lz == float_limit then (
            try ( z = lz[#Limited_Controller__Bezier_Float].value ) catch ( z = lz.value )
        ) else z = zp[#Z_Position].value
    ) catch ()
    -- Fold any FROZEN_POSITION drift into ZERO, then clear FROZEN (travel only on ZERO).
    local fv = [0, 0, 0]
    try ( fv = ctrl.pos.controller[1].value ) catch ()
    if abs fv.x > 0.0001 or abs fv.y > 0.0001 or abs fv.z > 0.0001 then (
        x += fv.x; y += fv.y; z += fv.z
        try ( ctrl.pos.controller[1].value = [0, 0, 0] ) catch ()
    )
    local nx = x
    local ny = y
    local nz = z
    if lim[3] == 0 and lim[4] == 0 then nx = 0.0
    else (
        if lim[3] == 1 and nx < lim[1] then nx = lim[1]
        if lim[4] == 1 and nx > lim[2] then nx = lim[2]
    )
    if lim[7] == 0 and lim[8] == 0 then ny = 0.0
    else (
        if lim[7] == 1 and ny < lim[5] then ny = lim[5]
        if lim[8] == 1 and ny > lim[6] then ny = lim[6]
    )
    if lim[11] == 0 and lim[12] == 0 then nz = 0.0
    else (
        if lim[11] == 1 and nz < lim[9] then nz = lim[9]
        if lim[12] == 1 and nz > lim[10] then nz = lim[10]
    )
    if abs (nx - x) > 0.0001 or abs (ny - y) > 0.0001 or abs (nz - z) > 0.0001 or abs fv.x > 0.0001 or abs fv.y > 0.0001 or abs fv.z > 0.0001 then (
        setLimitedAxisValue zp #X_Position nx
        setLimitedAxisValue zp #Y_Position ny
        setLimitedAxisValue zp #Z_Position nz
        true
    ) else false
)

fn mh2max_clampAll = (
    if mh2max_clampBusy == true then return false
    mh2max_clampBusy = true
    try (
        for c in mh2max_clampCtrls where (c != undefined and isValidNode c) do mh2max_clampOne c
    ) catch ()
    mh2max_clampBusy = false
    true
)

fn mh2max_onPostXform = (
    if mh2max_clampBusy == true then return false
    local n = undefined
    try ( n = callbacks.notificationParam() ) catch ()
    if n == undefined then return false
    if findItem mh2max_clampCtrls n == 0 then return false
    mh2max_clampBusy = true
    try ( mh2max_clampOne n ) catch ()
    mh2max_clampBusy = false
    true
)

fn mh2max_installClamps ctrls = (
    try ( deleteAllChangeHandlers id:#mh2maxLimClamp ) catch ()
    try ( callbacks.removeScripts id:#mh2maxLimClamp ) catch ()
    mh2max_clampCtrls = for c in ctrls where (c != undefined and isValidNode c) collect c
    -- Soft clamp only: per-node when-transform storms can black out Max UI
    try (
        callbacks.addScript #nodePostTransform "try(mh2max_onPostXform())catch()" id:#mh2maxLimClamp persistent:true
    ) catch ()
    -- Re-arm after file open (persistent callback script string survives; array of nodes must be rebuilt)
    try (
        callbacks.addScript #filePostOpen "try(mh2max_rearmClampsFromProps())catch()" id:#mh2maxLimClamp persistent:true
    ) catch ()
    mh2max_clampCtrls.count
)

fn mh2max_rearmClampsFromProps = (
    local ctrls = #()
    for o in objects where (matchPattern o.name pattern:"CTRL_*") do (
        local s = getUserProp o "mh2max_lim"
        if s != undefined and s != "" then append ctrls o
    )
    mh2max_installClamps ctrls
    -- also snap any drifted unlocked axes now
    try ( mh2max_clampAll() ) catch ()
    true
)

fn wireChannel morphMod ch src axis poseVal = (
    local axc = getAxisCtrl src axis
    if axc == undefined then throw ("no axis ctrl " + src.name + " " + axis)
    WM3_MC_SetValue morphMod ch 0.0
    local sc = float_script()
    sc.addTarget "cval" axc
    if poseVal > 0 then sc.script = "if cval > 0 then cval * 100 else 0"
    else sc.script = "if cval < 0 then -cval * 100 else 0"
    morphMod[ch].controller = sc
)

-- Corner residual channel: weight = |x|*|y| in the matching sign quadrant.
-- Reproduces RigLogic corner poses that linear X+Y morph summing misses.
fn wireComboChannel morphMod ch src sx sy = (
    local cx = getAxisCtrl src "X"
    local cy = getAxisCtrl src "Y"
    if cx == undefined or cy == undefined then throw ("no axis ctrl " + src.name + " XY")
    WM3_MC_SetValue morphMod ch 0.0
    local sc = float_script()
    sc.addTarget "cvx" cx
    sc.addTarget "cvy" cy
    local ex = if sx > 0 then "(if cvx > 0 then cvx else 0)" else "(if cvx < 0 then -cvx else 0)"
    local ey = if sy > 0 then "(if cvy > 0 then cvy else 0)" else "(if cvy < 0 then -cvy else 0)"
    sc.script = ex + " * " + ey + " * 100"
    morphMod[ch].controller = sc
)

fn bandC o zMode frac = (
    if o == undefined then return undefined
    local m = snapshotAsMesh o
    local zMin = 1e9
    local zMax = -1e9
    local pts = #()
    for i = 1 to m.numverts do (
        local p = getVert m i
        append pts p
        if p.z < zMin then zMin = p.z
        if p.z > zMax then zMax = p.z
    )
    delete m
    local h = zMax - zMin
    if h < 0.0001 then return undefined
    local thr = if zMode == #low then (zMin + h * frac) else (zMax - h * frac)
    local acc = [0,0,0]
    local cnt = 0
    for p in pts do (
        if (zMode == #low and p.z <= thr) or (zMode == #high and p.z >= thr) then (acc += p; cnt += 1)
    )
    if cnt == 0 then undefined else #(acc / cnt, zMin, zMax, cnt)
)

fn makeOpaqueMat nm r g b = (
    local m = PhysicalMaterial()
    m.name = nm
    m.base_color = color r g b
    m.base_weight = 1.0
    try ( m.transparency = 0.0 ) catch ()
    try ( m.roughness = 0.55 ) catch ()
    try ( m.metalness = 0.0 ) catch ()
    try ( m.thin_walled = false ) catch ()
    try ( m.cutout_map = undefined ) catch ()
    m
)

fn forceOpaqueMat o matName r g b = (
    if o == undefined then return false
    o.material = makeOpaqueMat matName r g b
    try ( o.xray = false ) catch ()
    true
)

fn hideBonesSilent = (
    local ly = ensureLayer "SkeletonBones"
    local n = 0
    for o in objects do (
        local cname = (classOf o) as string
        local boneLike = (cname == "BoneGeometry" or cname == "Biped_Object" or matchPattern o.name pattern:"bip_*")
        local helperLike = (cname == "Dummy" or cname == "Point" or cname == "ExposeTm") and (matchPattern o.name pattern:"*bone*" or matchPattern o.name pattern:"DEF_*" or matchPattern o.name pattern:"spine_*" or matchPattern o.name pattern:"clavicle_*" or matchPattern o.name pattern:"upperarm_*" or matchPattern o.name pattern:"thigh_*" or matchPattern o.name pattern:"neck_*" or matchPattern o.name pattern:"pelvis*")
        if boneLike or helperLike then (
            ly.addNode o
            hide o
            n += 1
        )
    )
    try ( ly.ishidden = true ) catch ()
    n
)

-- ========== MAIN (with progress + result dialog) ==========
mxImportOk = false
mxImportErr = ""
mxImportSummary = ""
try (
deleteFile mxLog
logf ("START " + localTime)
logf ("char=" + (mh2max_character as string) + " bodyType=" + (mh2max_bodyType as string))
logf ("fbx=" + mxFbx)

-- Reset first (destroys dialogs), then show progress overlay
resetMaxFile #noPrompt
logf "scene reset"
mh2max_progBegin()
mh2max_prog 2 "场景已重置，开始装配…"
try ( deleteAllChangeHandlers id:#mh2maxLimClamp ) catch ()
try ( callbacks.removeScripts id:#mh2maxLimClamp ) catch ()
mh2max_clampBusy = false
mh2max_clampCtrls = #()

if not doesFileExist mxFbx then throw ("MISSING FBX " + mxFbx)
-- v1.3.31: Maya file is Y-up; Max host is always Z-up.
-- FBX rotates each imported ROOT 90 deg so the whole tree (Skin/IK/ctrls/joints) stands up.
-- Morph OBJ import already applies the same Y-up→Z-up as eulerAngles -90 0 0.
-- UpAxis "Y" (v1.3.28) skipped that conversion and left the character on its side.
try (
    FBXImporterSetParam "ResetImport"
    FBXImporterSetParam "AxisConversion" true
    FBXImporterSetParam "UpAxis" "Z"
    FBXImporterSetParam "Skin" true
    FBXImporterSetParam "SmoothingGroups" true
    FBXImporterSetParam "Mode" #create
    FBXImporterSetParam "Animation" false
    FBXImporterSetParam "Cameras" false
    FBXImporterSetParam "Lights" false
) catch (
    logf ("WARN FBXImporterSetParam failed: " + (getCurrentException() as string))
)
mh2max_prog 8 "导入 FBX 角色…"
importFile mxFbx #noprompt
logf ("imported fbx objects=" + (objects.count as string))
try (
    local probe = getNodeByName mxBodyName
    if probe == undefined then probe = getNodeByName "SM_Male_Body_01"
    if probe == undefined then probe = getNodeByName "body_lod0_mesh"
    if probe != undefined then (
        local sz = probe.max - probe.min
        logf ("fbx Z-up probe " + probe.name + " size=" + (sz as string) + " (standing: Z > Y)")
    )
) catch ()

-- Morph OBJs (Face + Teeth + optional eye folders)
mh2max_prog 12 "准备 Morph 目标…"
theLayer = ensureLayer "FaceMorpher"
theLayer.ishidden = on
mxMorphRoot = if mh2max_morphRoot == undefined then (getFilenamePath mxMorphDir) else mh2max_morphRoot
morphFiles = #()
if doesFileExist mxMorphDir then join morphFiles (getFiles (mxMorphDir + "\\*.obj"))
if doesFileExist mxMorphRoot then (
    local subDirs = getDirectories (mxMorphRoot + "\\*")
    for d in subDirs do join morphFiles (getFiles (d + "*.obj"))
)
-- unique by filename
(
    local seen = #()
    local uniq = #()
    for f in morphFiles do (
        local bn = toLower (getFilenameFile f)
        if findItem seen bn == 0 then (
            append seen bn
            append uniq f
        )
    )
    morphFiles = uniq
)
sort morphFiles
logf ("morph files=" + (morphFiles.count as string))
importedCnt = 0
(
    local totalM = morphFiles.count
    if totalM < 1 then totalM = 1
    local mi = 0
    for f in morphFiles do (
        mi += 1
        local n = getFilenameFile f
        if (getNodeByName n) == undefined then (
            -- v1.3.28: do not trust "$" selection; find the newly imported object by diff.
            local beforeObjs = objects as array
            importFile f #noprompt
            local newObj = undefined
            for o in objects do (
                if (findItem beforeObjs o) == 0 then (newObj = o; exit)
            )
            if newObj != undefined then (
                newObj.name = n
                rotate newObj (eulerAngles -90 0 0)
                resetXForm newObj
                collapseStack newObj
                theLayer.addNode newObj
                hide newObj
                importedCnt += 1
            )
        )
        if (mod mi 8 == 0) or (mi == morphFiles.count) then (
            local pct = 12 + ((mi * 28) / totalM)
            mh2max_prog pct ("导入 Morph " + (mi as string) + "/" + (morphFiles.count as string) + "…")
        )
    )
)
logf ("morph imported=" + (importedCnt as string))

mh2max_prog 42 "定位全部头部子网格…"
head = nodeBy mxHeadName
if head == undefined then head = findByPattern "head_lod0_mesh"
if head == undefined then throw "head_lod0_mesh missing"

morphBuckets = #()
try (
    morphBuckets = mh2max_bucketMorphTargets()
    -- Keep legacy head alias if bucket resolved a mesh
    if morphBuckets.count >= 1 and morphBuckets[1][1] != undefined then head = morphBuckets[1][1]
    targetLog = "targets"
    for j = 1 to mh2max_morphMeshJobs.count do (
        targetLog += " " + mh2max_morphMeshJobs[j][3] + "=" + (morphBuckets[j][2].count as string)
    )
    logf targetLog
) catch (
    logf ("WARN morph bucket failed: " + (getCurrentException() as string))
    morphBuckets = #()
)

fn buildAndWireMorphs meshNode targets label = (
    if meshNode == undefined or targets.count == 0 then return #(0, 0)
    -- IMPORTANT (Max 2017+): one Morpher can hold >100 channels by BuildFromNode(ch>100).
    -- Stacking multiple Morphers is NOT safely additive — jaw+eye (and similar) nonlinearly
    -- blows up mid-face (measured ~2x jaw delta in wrong direction). Keep a single Morpher.
    local wiredL = 0
    local failedL = 0
    local morphMod = Morpher()
    addModifier meshNode morphMod
    if targets.count > 100 then (
        logf ("morpher " + label + " channels=" + (targets.count as string) + " (expand past 100)")
    )
    for i = 1 to targets.count do (
        local nd = targets[i]
        local inf = parseMorphName nd.name
        local ch = i
        try (
            WM3_MC_BuildFromNode morphMod ch nd
            WM3_MC_SetName morphMod ch nd.name
            hide nd
            if inf == undefined then throw "parse fail"
            local src = getNodeByName inf[1]
            if src == undefined then throw ("missing ctrl " + inf[1])
            if inf[2] == "COMBO" then wireComboChannel morphMod ch src inf[3][1] inf[3][2]
            else wireChannel morphMod ch src inf[2] inf[3]
            wiredL += 1
        ) catch (
            failedL += 1
            if failedL <= 12 then logf ("wireFail " + label + " " + nd.name + " " + (getCurrentException()))
        )
    )
    try ( logf ("morpher " + label + " numChannels=" + ((WM3_NumberOfChannels morphMod) as string)) ) catch ()
    #(wiredL, failedL)
)

-- Limits FIRST so morph float_scripts bind to final ZERO_POS tracks
mh2max_prog 48 "应用控制器限位…"
limCount = 0
limFail = 0
limCtrls = #()
if doesFileExist mxLimits then (
    local f = openFile mxLimits
    local limLines = 0
    local limDone = 0
    -- count first for smoother bar
    while not eof f do (
        local ln = trimRight (readLine f)
        if ln.count > 0 then limLines += 1
    )
    close f
    f = openFile mxLimits
    while not eof f do (
        local ln = trimRight (readLine f)
        if ln.count > 0 then (
            local toks = filterString ln "\t"
            if toks.count >= 14 then (
                local cname = toks[1]
                if isSliderCtrl cname then (
                    local fname = toks[2]
                    local ctrl = nodeBy cname
                    local frm = if fname.count > 0 then nodeBy fname else undefined
                    if ctrl != undefined then (
                        try (
                            if frm != undefined and not isAncestor ctrl frm then (
                                if ctrl.parent != frm then keepWorldParent ctrl frm
                            )
                            -- Snap to FRM-local origin BEFORE FreezeTransform so FROZEN_POSITION
                            -- stays [0,0,0]. Travel must live only on ZERO_POS (float_limit).
                            -- If freeze runs while the knob is offset, FROZEN bakes that offset and
                            -- float_limit on ZERO cannot pull the knob back onto the FRM track.
                            try (
                                if ctrl.parent != undefined then (
                                    in coordsys parent ( ctrl.pos = [0, 0, 0] )
                                )
                            ) catch ()
                            freezeTransformOne ctrl
                            try ( ctrl.pos.controller[1].value = [0, 0, 0] ) catch ()
                            local lockBits = #{4,5,6,7,8,9}
                            if (toks[5] as integer) == 0 and (toks[6] as integer) == 0 then lockBits[1] = true
                            if (toks[9] as integer) == 0 and (toks[10] as integer) == 0 then lockBits[2] = true
                            if (toks[13] as integer) == 0 and (toks[14] as integer) == 0 then lockBits[3] = true
                            setTransformLockFlags ctrl lockBits
                            applyLimitFloat ctrl "x" (toks[3] as float) (toks[4] as float) (toks[5] as integer) (toks[6] as integer)
                            applyLimitFloat ctrl "y" (toks[7] as float) (toks[8] as float) (toks[9] as integer) (toks[10] as integer)
                            applyLimitFloat ctrl "z" (toks[11] as float) (toks[12] as float) (toks[13] as integer) (toks[14] as integer)
                            setUserProp ctrl "mh2max_lim" (
                                toks[3] + "," + toks[4] + "," + toks[5] + "," + toks[6] + "," +
                                toks[7] + "," + toks[8] + "," + toks[9] + "," + toks[10] + "," +
                                toks[11] + "," + toks[12] + "," + toks[13] + "," + toks[14]
                            )
                            append limCtrls ctrl
                            limCount += 1
                        ) catch (
                            limFail += 1
                            if limFail <= 8 then logf ("limFail " + cname + " " + (getCurrentException()))
                        )
                    )
                )
            )
            limDone += 1
            if (mod limDone 20 == 0) or (limDone == limLines) then (
                local denom = if limLines > 0 then limLines else 1
                mh2max_prog (48 + ((limDone * 10) / denom)) ("应用限位 " + (limCount as string) + "…")
            )
        )
    )
    close f
)
logf ("limits ok=" + (limCount as string) + " fail=" + (limFail as string))

-- Morph wiring AFTER limits so float_script targets Limited_Controller tracks
mh2max_prog 60 "装配全部头部 Morpher（Face/牙/牙龈/眼…）…"
wired = 0
failed = 0
faceWired = 0
teethWired = 0
salivaWired = 0
try (
    for j = 1 to mh2max_morphMeshJobs.count do (
        local job = mh2max_morphMeshJobs[j]
        local label = job[3]
        local pct = 60 + ((j * 10) / mh2max_morphMeshJobs.count)
        mh2max_prog pct ("装配 " + label + " Morpher…")
        if j > morphBuckets.count then (
            logf ("WARN morph bucket missing for " + label)
            continue
        )
        local res = buildAndWireMorphs morphBuckets[j][1] morphBuckets[j][2] label
        wired += res[1]
        failed += res[2]
        if label == "face" then faceWired = res[1]
        else if label == "teeth" then teethWired = res[1]
        else if label == "saliva" then salivaWired = res[1]
    )
) catch (
    logf ("WARN morph wiring failed: " + (getCurrentException() as string))
)
logf ("wired=" + (wired as string) + " failed=" + (failed as string) +
    " (face=" + (faceWired as string) +
    " teeth=" + (teethWired as string) +
    " saliva=" + (salivaWired as string) +
    " other=" + ((wired - faceWired - teethWired - salivaWired) as string) + ")")

mh2max_prog 72 "布局 Face GUI…"
body = findBodyMesh()
bodyGrp = nodeBy mxBodyGrpName
if bodyGrp == undefined then bodyGrp = findByPattern "body_lod0_grp"
headRoot = nodeBy mxHeadGrpName
if headRoot == undefined then headRoot = findByPattern "head_grp"
if headRoot == undefined then headRoot = head
gui = nodeBy mxGuiName
guiRoot = nodeBy mxGuiGrpName
if guiRoot == undefined then guiRoot = findByPattern "GRP_faceGUI"
if guiRoot == undefined then guiRoot = findByPattern "headGui_grp"
if guiRoot == undefined then guiRoot = gui
comb = findCombinedMesh()
moverBody = if bodyGrp != undefined then bodyGrp else body

logf ("head=" + (if head != undefined then head.name else "MISS"))
logf ("body=" + (if body != undefined then body.name else "MISS"))
logf ("mover=" + (if moverBody != undefined then moverBody.name else "MISS"))
logf ("guiRoot=" + (if guiRoot != undefined then guiRoot.name else "MISS"))

-- Detach body from head so moving one does not drag the other
if moverBody != undefined and headRoot != undefined then (
    if isAncestor headRoot moverBody then (
        detachKeepWorld moverBody
        logf ("detached " + moverBody.name + " from head hierarchy")
    )
)

-- Preserve FBX head/body relative pose completely (no geo yank).
logf "skip geo align (preserve FBX head/body pose)"

-- Place face GUI to the right of the head (character +X)
if guiRoot != undefined and head != undefined then (
    in coordsys world (
        local hmax = head.max
        local hmin = head.min
        local hcen = (hmin + hmax) * 0.5
        local headW = hmax.x - hmin.x
        local pad = amax (headW * 0.25) 1.5
        local g = guiRoot
        -- If GUI is at feet / origin, or overlapping the skull, relocate the whole GUI group
        local gpos = g.pos
        local atFeet = gpos.z < (hmin.z - 10.0)
        local tooLeft = gpos.x < (hcen.x)
        if atFeet or tooLeft then (
            local target = [hmax.x + pad + 2.0, hmin.y - 0.2, hcen.z]
            logf ("gui " + g.name + " " + (gpos as string) + " -> " + (target as string))
            g.pos = target
        ) else (
            -- Nudge X so panel sits to the right of the head bbox
            local gx = g.pos.x
            if gx < (hmax.x + 0.5) then (
                g.pos = [hmax.x + pad + 2.0, g.pos.y, g.pos.z]
                logf ("gui nudged X to " + (g.pos as string))
            ) else logf ("gui keep " + (g.pos as string))
        )
    )
)

-- Re-zero slider ZERO_POS layer only (not GUI root / FRM)
nZero = 0
for o in objects do (
    if isSliderCtrl o.name and o.parent != undefined and (matchPattern o.parent.name pattern:"FRM_*") then (
        try (
            ensureZeroPosXYZ o
            local zp = o.pos.controller.ZERO_POS_XYZ.controller
            for key in #(#X_Position, #Y_Position, #Z_Position) do (
                try (
                    local lim = zp[key].controller
                    if classOf lim == Float_Limit or classOf lim == float_limit then (
                        try ( lim[#Limited_Controller__Bezier_Float].value = 0.0 ) catch ( lim.value = 0.0 )
                    ) else (
                        zp[key].value = 0.0
                    )
                ) catch ()
            )
            nZero += 1
        ) catch ()
    )
)
logf ("sliders rezeroed=" + (nZero as string))

-- Wire CTRL → facial bones (Skin-safe).
-- CRITICAL: Do NOT use Rotation_list on skinned joints.
-- float_script on Euler axis returns RADIANS; display ≈ D0 + rad2deg(script).
-- Probe D0 with script "0", then scriptBind = displayBind - D0.
-- NEVER assign Euler using script-space angles (e.g. -130) — Max remaps them.
fn mh2max_findBoneBySuffix nm = (
    local o = getNodeByName nm exact:true ignoreCase:false
    if o != undefined then return o
    o = getNodeByName ("MHHead:" + nm) exact:true ignoreCase:false
    if o != undefined then return o
    for obj in objects where matchPattern obj.name pattern:("*" + nm) do return obj
    undefined
)

fn mh2max_ensureEuler b = (
    local rc = b.rotation.controller
    if not (classof rc == Euler_XYZ or classof rc == Euler_Xyz) then (
        local dx = 0.0; local dy = 0.0; local dz = 0.0
        try ( local e = b.rotation as eulerAngles; dx = e.x; dy = e.y; dz = e.z ) catch ()
        b.rotation.controller = Euler_Xyz()
        b.rotation.x_rotation = dx; b.rotation.y_rotation = dy; b.rotation.z_rotation = dz
    )
)

fn mh2max_axisGet b rotAxis = (
    if rotAxis == "Y" or rotAxis == "y" then return b.rotation.y_rotation
    if rotAxis == "Z" or rotAxis == "z" then return b.rotation.z_rotation
    b.rotation.x_rotation
)

fn mh2max_axisSetFloat b rotAxis ctrl = (
    if rotAxis == "Y" or rotAxis == "y" then b.rotation.y_rotation.controller = ctrl
    else if rotAxis == "Z" or rotAxis == "z" then b.rotation.z_rotation.controller = ctrl
    else b.rotation.x_rotation.controller = ctrl
)

fn mh2max_axisSetValue b rotAxis v = (
    if rotAxis == "Y" or rotAxis == "y" then b.rotation.y_rotation = v
    else if rotAxis == "Z" or rotAxis == "z" then b.rotation.z_rotation = v
    else b.rotation.x_rotation = v
)

fn mh2max_probeScript0 b rotAxis = (
    mh2max_ensureEuler b
    local dSave = mh2max_axisGet b rotAxis
    mh2max_axisSetFloat b rotAxis (bezier_float())
    mh2max_axisSetValue b rotAxis dSave
    local sc = float_script(); sc.script = "0"
    mh2max_axisSetFloat b rotAxis sc
    local d0 = mh2max_axisGet b rotAxis
    mh2max_axisSetFloat b rotAxis (bezier_float())
    mh2max_axisSetValue b rotAxis dSave
    d0
)

fn mh2max_wireBoneRot1 boneNode axc scaleDeg rotAxis propTag = (
    if boneNode == undefined or axc == undefined then return false
    try ( axc.value = 0.0 ) catch ()
    mh2max_ensureEuler boneNode
    -- NEVER force a hardcoded bind (e.g. -40). That destroyed Skin on this MetaHuman.
    -- Use current display angle + probe D0 → scriptBind = dBind - D0.
    local dBind = mh2max_axisGet boneNode rotAxis
    local d0 = mh2max_probeScript0 boneNode rotAxis
    local scriptBind = dBind - d0
    local sc = float_script()
    sc.addTarget "cval" axc
    sc.script = "degToRad ((" + (scriptBind as string) + ") + cval * (" + (scaleDeg as string) + "))"
    mh2max_axisSetFloat boneNode rotAxis sc
    setUserProp boneNode "mh2max_boneWire" (propTag + " dBind=" + (dBind as string) + " sBind=" + (scriptBind as string))
    true
)

fn mh2max_wireBoneRotMulti boneNode targets rotAxis propTag = (
    if boneNode == undefined or targets == undefined or targets.count == 0 then return false
    for t in targets do ( try ( t[1].value = 0.0 ) catch () )
    mh2max_ensureEuler boneNode
    local dBind = mh2max_axisGet boneNode rotAxis
    local d0 = mh2max_probeScript0 boneNode rotAxis
    local scriptBind = dBind - d0
    local sc = float_script()
    local expr = ""
    for i = 1 to targets.count do (
        local nm = "c" + (i as string)
        sc.addTarget nm targets[i][1]
        if i > 1 then expr += " + "
        expr += nm + "*" + (targets[i][2] as string)
    )
    sc.script = "degToRad ((" + (scriptBind as string) + ") + (" + expr + "))"
    mh2max_axisSetFloat boneNode rotAxis sc
    setUserProp boneNode "mh2max_boneWire" (propTag + " dBind=" + (dBind as string) + " sBind=" + (scriptBind as string))
    true
)

fn mh2max_wireBonePos1 boneNode axc scaleFactor posAxis propTag = (
    if boneNode == undefined or axc == undefined then return false
    try ( axc.value = 0.0 ) catch ()
    local px = 0.0; local py = 0.0; local pz = 0.0
    local pc = boneNode.pos.controller
    if classOf pc == Position_List or classOf pc == position_list then (
        try (
            local fr = pc[1].controller
            px = fr.x_position; py = fr.y_position; pz = fr.z_position
        ) catch (
            px = boneNode.pos.x; py = boneNode.pos.y; pz = boneNode.pos.z
        )
    ) else if classOf pc == Position_XYZ or classOf pc == position_xyz then (
        px = pc.x_position; py = pc.y_position; pz = pc.z_position
    ) else (
        px = boneNode.pos.x; py = boneNode.pos.y; pz = boneNode.pos.z
    )
    local fr = Position_XYZ()
    fr.x_position = px; fr.y_position = py; fr.z_position = pz
    boneNode.position.controller = fr
    local sc = float_script()
    sc.addTarget "cval" axc
    local bindP = py
    if posAxis == "X" or posAxis == "x" then bindP = px
    else if posAxis == "Z" or posAxis == "z" then bindP = pz
    sc.script = "(" + (bindP as string) + ") + cval * (" + (scaleFactor as string) + ")"
    if posAxis == "X" or posAxis == "x" then
        boneNode.pos.controller.x_position.controller = sc
    else if posAxis == "Z" or posAxis == "z" then
        boneNode.pos.controller.z_position.controller = sc
    else
        boneNode.pos.controller.y_position.controller = sc
    setUserProp boneNode "mh2max_boneWire" propTag
    true
)

fn mh2max_wireBonePos2 boneNode axc scaleY scaleZ propTag = (
    if boneNode == undefined or axc == undefined then return false
    try ( axc.value = 0.0 ) catch ()
    local px = 0.0; local py = 0.0; local pz = 0.0
    local pc = boneNode.pos.controller
    if classOf pc == Position_List or classOf pc == position_list then (
        try (
            local fr = pc[1].controller
            px = fr.x_position; py = fr.y_position; pz = fr.z_position
        ) catch (
            px = boneNode.pos.x; py = boneNode.pos.y; pz = boneNode.pos.z
        )
    ) else if classOf pc == Position_XYZ or classOf pc == position_xyz then (
        px = pc.x_position; py = pc.y_position; pz = pc.z_position
    ) else (
        px = boneNode.pos.x; py = boneNode.pos.y; pz = boneNode.pos.z
    )
    local fr = Position_XYZ()
    fr.x_position = px; fr.y_position = py; fr.z_position = pz
    boneNode.position.controller = fr
    local scY = float_script(); scY.addTarget "cval" axc
    scY.script = "(" + (py as string) + ") + cval * (" + (scaleY as string) + ")"
    local scZ = float_script(); scZ.addTarget "cval" axc
    scZ.script = "(" + (pz as string) + ") + cval * (" + (scaleZ as string) + ")"
    boneNode.pos.controller.y_position.controller = scY
    boneNode.pos.controller.z_position.controller = scZ
    setUserProp boneNode "mh2max_boneWire" propTag
    true
)

fn mh2max_wireAllOralBones = (
    -- SAFETY: imported FBX already contains the exact Maya bind matrices.
    -- Replacing controllers on skinned FACIAL joints changes their evaluated
    -- matrices and permanently tears the lower face. Keep every facial joint
    -- exactly as imported until a matrix-preserving driver is implemented.
    logf "oralBoneWires=SKIPPED (preserve Maya FBX bind matrices)"
    true
)

-- DO NOT reset Euler on oral bones (destroys Skin bind). Skin-safe Euler+script only.

mh2max_prog 78 "保留 Maya 面部骨骼绑定矩阵…"
try (
    if mh2max_wireAllOralBones() then logf "oral bone wires=all OK"
    else logf "oral bone wires=partial"
) catch (
    logf ("oral bone wires FAIL " + (getCurrentException() as string))
)

-- Viewport materials: kill DirectX alpha sorting / see-through (except hair)
mh2max_prog 80 "整理视口材质 / 隐藏骨骼…"
fn isHairLike nm = (
    local low = toLower nm
    (matchPattern low pattern:"*hair*") or (matchPattern low pattern:"*groom*") or (matchPattern low pattern:"*fur*") or (matchPattern low pattern:"*card*")
)

fn forceOpaqueAllMeshes = (
    local n = 0
    for o in geometry do (
        local nm = o.name
        if isHairLike nm then (
            logf ("keep hair/groom mat: " + nm)
        ) else (
            local r = 200; local g = 160; local b = 135
            local low = toLower nm
            if matchPattern low pattern:"*teeth*" then (r=240; g=235; b=225)
            else if matchPattern low pattern:"*eye*" then (r=230; g=230; b=230)
            else if matchPattern low pattern:"*lash*" then (r=25; g=18; b=12)
            -- head + body share one skin tone so the neck seam matches in viewport
            else if (matchPattern low pattern:"*body*") or (matchPattern low pattern:"*head*") then (
                r=200; g=160; b=135
            )
            forceOpaqueMat o ("mh_vp_" + nm) r g b
            try ( o.xray = false ) catch ()
            try ( o.backFaceCull = false ) catch ()
            -- Kill opacity maps that cause viewport sorting ghosts
            try (
                if o.material != undefined then (
                    try ( o.material.cutout_map = undefined ) catch ()
                    try ( o.material.opacity = 100 ) catch ()
                    try ( o.material.transparency = 0.0 ) catch ()
                )
            ) catch ()
            n += 1
        )
    )
    n
)

opaqueN = forceOpaqueAllMeshes()
logf ("opaque meshes=" + (opaqueN as string))

-- Hide shells / saliva that cause mouth/arm see-through in viewport
for n in #("eyeshell_lod0_mesh", "eyeEdge_lod0_mesh", "saliva_lod0_mesh", "cartilage_lod0_mesh") do (
    local o = nodeBy n
    if o == undefined then o = findByPattern ("*" + n)
    if o != undefined then (
        hide o
        logf (o.name + " hidden (viewport see-through)")
    )
)

if comb != undefined then (
    hide comb
    logf (comb.name + " hidden (combined duplicate)")
)
if head != undefined then (
    head.xray = false
    head.backFaceCull = false
)

-- Bones on layer (imported, hidden for clean viewport — still in scene)
bn = hideBonesSilent()
logf ("bones on SkeletonBones layer, hidden=" + (bn as string))

-- Body controllers: FBX only (no Max-side constraint rewire)
try ( wireBodyLinksFromFile() ) catch ( logf ("body wire FAIL " + (getCurrentException() as string)) )

-- Freeze face GUI frames / labels; CTRL knobs stay draggable
mh2max_prog 88 "冻结 GUI / 安装限位钳制…"
frozenN = freezeGuiDecor()
logf ("gui decor frozen=" + (frozenN as string))
clampN = mh2max_installClamps limCtrls
logf ("viewport clamps=" + (clampN as string))
try ( toolMode.coordsys = #parent ) catch ()
try ( setRefCoordSys #parent ) catch ()

-- Face-on viewport + beauty display (renderable only). No scene camera.
mh2max_prog 94 "设置正面视口 / 仅显示可渲染项…"
faceViewOk = false
vis = #(0, 0)
try (
    faceViewOk = mh2max_frameFaceFront head
    if faceViewOk then logf "faceView=persp_user (no camera)"
    else logf "faceView=FAIL"
) catch (
    logf ("faceView FAIL " + (getCurrentException() as string))
    faceViewOk = false
)
try ( mh2max_deleteFaceCameras() ) catch ()
try (
    vis = mh2max_showOnlyRenderable keepNodes:#()
    logf ("viewport renderable show=" + (vis[1] as string) + " hide=" + (vis[2] as string))
) catch (
    logf ("showOnlyRenderable FAIL " + (getCurrentException() as string))
    vis = #(0, 0)
)

mh2max_prog 98 "保存场景…"
if head != undefined then logf ("final head bbox " + (head.min as string) + ".." + (head.max as string))
if body != undefined then logf ("final body bbox " + (body.min as string) + ".." + (body.max as string))
if gui != undefined then (in coordsys world (logf ("final CTRL_faceGUI " + (gui.pos as string))))
if guiRoot != undefined then (in coordsys world (logf ("final guiRoot " + (guiRoot.pos as string))))

local mh2max_savedFiles = mh2max_saveArchives mxSaveBase
logf ("archived " + (mh2max_savedFiles.count as string) + " max file(s)")
logf "DONE"

mh2max_prog 100 "完成"
local mxSavedList = ""
for sp in mh2max_savedFiles do mxSavedList += sp + "\n"
mxImportSummary = "MetaHuman 已导入 3ds Max。\n\n" +
    "角色：" + ((mh2max_character as string)) + "\n" +
    "体型：" + ((mh2max_bodyType as string)) + "\n\n" +
    "Morph 导入：" + (importedCnt as string) + "\n" +
    "限位成功：" + (limCount as string) + "  失败：" + (limFail as string) + "\n" +
    "Morph 连线：" + (wired as string) + "  失败：" + (failed as string) + "\n" +
    "视口钳制：" + (clampN as string) + "\n" +
    "可渲染显示：" + (vis[1] as string) + " / 已隐藏：" + (vis[2] as string) + "\n\n" +
    "已归档：\n" + mxSavedList + "\n" +
    "日志：\n" + mxLog
mxImportOk = true
) catch (
    mxImportErr = getCurrentException() as string
    try ( logf ("FAIL " + mxImportErr) ) catch ()
)
mh2max_progEnd()
if mxImportOk then (
    messageBox mxImportSummary title:"mh2max 导入完成" beep:false
) else (
    messageBox ("装配失败：\n\n" + mxImportErr + "\n\n请查看日志：\n" + (mxLog as string)) title:"mh2max 导入失败" beep:true
)
mxImportOk
